from benchmark import Benchmark


def main():
    benchmark = (
        Benchmark()
        .addLLM("gpt")
        .addLLM("gpt4")
        .configureGame()
            .setGameSize(16)
            .setLanguageConfig({"German": 2, "English": 5})
            .done()
        .build()
    )

    print(benchmark.summary())

    benchmark.runBenchmarkSet()


if __name__ == "__main__":
    main()