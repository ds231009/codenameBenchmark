from ustp_ccl_benchmark.logging_utils import log

CODEMASTER_PROMPT = """
You are playing a game of Codemaster in the role of the CODEMASTER.
You will receive a list of words on a board, each assigned to a group: <blue | red | assassin>.

Your objective is to help your partner (the Guesser) identify all the "blue" words in as few
turns as possible, without them guessing "red" words or the "assassin" word.

### Rules & Scoring:
* Your partner must guess the "blue" words based on the clue you provide.
* +1 point for every correctly guessed "blue" word.
* -1 point if your partner guesses a "red" word.
* GAME OVER (You lose) if your partner guesses the "assassin" word.

### Move Constraints:
* You must provide exactly ONE clue per turn.
* The clue word MUST be a valid English word.
* The clue word MUST NOT share the same word stem as any word currently visible on the board.

### Output Format:
You must reply with a single tuple containing your clue word and the number of board words it
connects to. Your partner will make their guess based on this clue. Count has to be >0.
Return ONLY this strict tuple format: (word, count)

Few-shot examples:
(ocean, 2)
(greek, 1)
""".strip()

GUESSER_PROMPT = """
You are playing a game of Codemaster in the role of the GUESSER.
You will receive a list of available words on a board and a clue from your partner (the Codemaster).

Your objective is to guess the hidden "blue" words based on the Codemaster's clues in as few
turns as possible, while avoiding "red" words and the "assassin" word.

### Rules & Scoring:
* +1 point for every correctly guessed "blue" word.
* -1 point if you guess a "red" word.
* GAME OVER (You lose) if you guess the "assassin" word.

### Move Instructions:
* You must perform a single move by making one guess at a time.
* The word you guess MUST be chosen from the provided board.
* The word MUST be spelled exactly as it appears on the board.
* If you are unsure and want to end your turn, you can choose to pass.

### Output Format:
If you want to guess a word, output ONLY the word enclosed in brackets:
[word]

If you do not want to guess anything, output ONLY this exact string:
[no guess]
""".strip()


class LLM():
    def __init__(self, base_llm, config, role):
        self.base_llm = base_llm
        self.modelName = base_llm.get_model_name() if hasattr(base_llm, 'get_model_name') else config.get("modelName", "Unknown")
        self.role = role
        self.prompt = CODEMASTER_PROMPT if role == "Codemaster" else GUESSER_PROMPT
        self.strategy_refinement = ""

        # ------------------------------------------------------------------
        # Call log: every individual LLM invocation (a move, or a refinement
        # attempt) is appended here as {role, call_type, prompt, response}.
        # GameSet drains this via pop_new_calls() after each game / refinement
        # step so it can attribute each call to the right point in the run
        # for the detailed live-output log.
        #
        # log_calls is a master on/off switch (set by GameSet based on its
        # enable_live_output flag). When False, nothing is appended at all --
        # this matters because a long benchmark run reuses the same LLM
        # instance across every game, so an unbounded call_log would just be
        # wasted memory when nobody wants the detailed log.
        # ------------------------------------------------------------------
        self.call_log = []
        self.log_calls = True

        self.clearMemory()
        
    def _trim_history(self):
        """Keeps the system prompt plus the most recent MAX_HISTORY_TURN_PAIRS
        user/assistant pairs, dropping older turns from the front."""
        system_msgs = self.history[:1]
        turn_msgs = self.history[1:]
        max_msgs = self.MAX_HISTORY_TURN_PAIRS * 2
        if len(turn_msgs) > max_msgs:
            turn_msgs = turn_msgs[-max_msgs:]
        self.history = system_msgs + turn_msgs

    def getLLMResponse(self, board, clue=None, feedback=None):
        turn_content = f"This is the current board as an array: {board}"

        if feedback:
            turn_content = f"FEEDBACK FROM LAST TURN: {feedback}\n\n" + turn_content

        if self.role == "Guesser" and clue:
            turn_content = (
                f"This is your partners clue: {clue}. The word hints towards the word your partner "
                f"wants you to guess. The number implies the number of words the clue is meant for\n\n"
                + turn_content
            )

        self.history.append({'role': 'user', 'content': turn_content})
        self._trim_history()
        response = self.callLLM()
        self.history.append({'role': 'assistant', 'content': response})

        if self.log_calls:
            self.call_log.append({
                "role": self.role,
                "call_type": "move",
                "prompt": turn_content,
                "response": response,
            })

        return response

    # ------------------------------------------------------------------
    # Reflection / continuous learning
    # ------------------------------------------------------------------

    # Conservative char budget for the history block inside a reflection prompt.
    # The model that triggered 400 errors has an 8192-token context with
    # max_tokens=4096, leaving 4096 tokens for input. German compound words
    # tokenize at roughly 2.4 chars/token on Gemma, not the 4.0 often assumed.
    # Fixed overhead (system msg + reflection template) ~= 200 tokens ~= 480 chars.
    # That leaves (4096 - 200) * 2.4 = ~9,350 chars -- but we want headroom for
    # variance, so we cap at 3,000. Adjust upward on larger-context models.
    REFLECTION_HISTORY_CHAR_LIMIT = 3_000

    @staticmethod
    def _build_compact_history(refinement_batch, char_limit: int) -> tuple[str, bool]:
        """Render the batch as a terse, token-efficient transcript and truncate
        to char_limit if needed.

        Compact format (one line per turn instead of one verbose sentence):
            G1(WIN):  (GEWINDE,1) -> SCHRAUBE[blue+1]
            G2(LOSS): (TAG,1) -> ASSASSIN[assassin-25]

        Returns (history_text, was_truncated).
        """
        import re

        lines = []
        for game in refinement_batch:
            outcome = game.get("outcome", "?")
            header = f"G{game['game_index']}({outcome}):"

            if not game['turn_history']:
                lines.append(f"{header} no turns")
                continue

            for turn_line in game['turn_history']:
                # Original verbose format:
                #   "- Turn 1: You gave clue (WORD, N). Guesser picked: 'X' (which was group)."
                # We compress it to:
                #   "G1(WIN): T1 (WORD,N) -> X[group]"
                turn_num = re.search(r'Turn (\d+)', turn_line)
                clue_match = re.search(r'\(([A-ZÄÖÜ]+),\s*(\d+)\)', turn_line)
                picks = re.findall(r"'([^']+)' \(which was (\w+)\)", turn_line)

                t = f"T{turn_num.group(1)}" if turn_num else "T?"
                clue_str = f"({clue_match.group(1)},{clue_match.group(2)})" if clue_match else "(?,?)"
                if picks:
                    pick_str = ", ".join(f"{w}[{g}]" for w, g in picks)
                else:
                    pick_str = "pass"

                lines.append(f"{header} {t} {clue_str} -> {pick_str}")

        history_text = "\n".join(lines)

        truncated = False
        if len(history_text) > char_limit:
            history_text = history_text[:char_limit]
            history_text = history_text[:history_text.rfind("\n") + 1].rstrip()
            history_text += "\n[...truncated...]"
            truncated = True

        return history_text, truncated

    def writeRefinement(self, refinement_batch):
        """Generates a continuous learning strategy based on the past batch of games.

        Tries twice on context-overflow errors: first with the normal char limit,
        then with half of it. If both fail the refinement is skipped and an empty
        string is returned so the run can continue.

        Every attempt (successful or not) is recorded in self.call_log with its
        prompt and response (or error) so the live output can show exactly what
        was sent to the model and what came back.
        """
        limits_to_try = [
            self.REFLECTION_HISTORY_CHAR_LIMIT,
            self.REFLECTION_HISTORY_CHAR_LIMIT // 2,
        ]

        for attempt, limit in enumerate(limits_to_try, start=1):
            history_text, was_truncated = self._build_compact_history(refinement_batch, limit)

            if was_truncated:
                log(self.role, f"History truncated to {limit} chars (attempt {attempt}).", level="warning")

            reflection_prompt = (
                "Batch transcript:\n"
                f"{history_text}\n\n"
                "Write up to 5 concise strategic rules to improve future performance.\n"
                "Rules must be abstract -- no specific words from these games.\n"
                "Output ONLY the numbered rules, nothing else."
            )

            temp_history = [
                {'role': 'system', 'content': f"You are a Codenames {self.role} reviewing past games. Be concise."},
                {'role': 'user', 'content': reflection_prompt},
            ]

            log(self.role, f"Reflecting (attempt {attempt}, {len(history_text)} chars)...")

            try:
                new_strategy = self.callLLM(messages=temp_history)
                self.strategy_refinement = new_strategy

                if self.log_calls:
                    self.call_log.append({
                        "role": self.role,
                        "call_type": "refinement",
                        "attempt": attempt,
                        "prompt": reflection_prompt,
                        "response": new_strategy,
                    })

                return new_strategy

            except Exception as e:
                # Catch context-overflow (400 BadRequestError) and any other
                # transient failure so a bad refinement step never kills the run.
                if self.log_calls:
                    self.call_log.append({
                        "role": self.role,
                        "call_type": "refinement",
                        "attempt": attempt,
                        "prompt": reflection_prompt,
                        "response": None,
                        "error": str(e),
                    })

                is_context_error = "400" in str(e) or "context" in str(e).lower() or "input_tokens" in str(e).lower()
                if is_context_error and attempt < len(limits_to_try):
                    log(self.role, f"Context overflow on attempt {attempt} -- retrying with half the history.", level="warning")
                    continue
                log(self.role, f"Refinement failed after {attempt} attempt(s): {e}. Skipping.", level="error")
                return ""

        # Shouldn't be reachable, but keeps the return type consistent.
        return ""

    # ------------------------------------------------------------------
    # Call log
    # ------------------------------------------------------------------

    def pop_new_calls(self):
        """Drains and returns every call recorded since the last drain.

        Used by GameSet to attribute each LLM call (move or refinement) to
        the specific game / refinement step it happened during, for the
        detailed live-output log.
        """
        calls = self.call_log
        self.call_log = []
        return calls

    # ------------------------------------------------------------------
    # Memory
    # ------------------------------------------------------------------

    def clearMemory(self):
        """Wipes history but injects the learned strategy into the base prompt."""
        system_content = self.prompt
        if self.strategy_refinement:
            system_content += "\n\n### YOUR CONTINUOUS LEARNING STRATEGY (Follow these tips strictly):\n"
            system_content += self.strategy_refinement

        self.history = [{'role': 'system', 'content': system_content}]
        log(self.role, "Memory cleared. Base prompt and strategy loaded.")

    # ------------------------------------------------------------------
    # LLM dispatch
    # ------------------------------------------------------------------

    def callLLM(self, messages=None):
        msgs = messages if messages is not None else self.history

        langchain_msgs = []
        for m in msgs:
            if m['role'] == 'system':
                langchain_msgs.append(("system", m['content']))
            elif m['role'] == 'assistant':
                langchain_msgs.append(("ai", m['content']))
            else:
                langchain_msgs.append(("human", m['content']))

        if hasattr(self.base_llm, 'load_model'):
            response = self.base_llm.load_model().invoke(langchain_msgs)
            return response.content

        elif hasattr(self.base_llm, 'generate'):
            flat_prompt = "\n\n".join([f"{m['role'].upper()}: {m['content']}" for m in msgs])
            return self.base_llm.generate(flat_prompt)

        elif getattr(self.base_llm, 'type', None) == "debug":
            return input(f"\nDebug LLM Input for {self.role}: ")

        log(self.role, "No valid LLM configuration found for base_llm.", level="error")
        return "No valid LLM configuration found."

    def summary(self):
        summary_dict = {
            "name": self.modelName,
            "role": self.role,
            "prompt": self.prompt,
            "final_strategy": self.strategy_refinement,
        }
        if hasattr(self.base_llm, "get_metrics"):
            summary_dict["llm_metrics"] = self.base_llm.get_metrics()
        return summary_dict