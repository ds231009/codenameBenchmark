from .benchmark import BenchmarkSuite

benchmarkSuite = (
    BenchmarkSuite()
    .addModel({})
    .configureGame()
        .setDuration(4)
        .setRefinementStep(2)
        .setGroupConfig({"blue": 1, "red": 1, "assassin": 2})
        .setLanguageConfig({"German": 2, "English": 5})
        .done()
    .build()
)

print(benchmarkSuite.summary())
benchmarkSuite.runBenchmarkSet()