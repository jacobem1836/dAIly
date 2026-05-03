pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
        maven("https://jitpack.io")  // REQUIRED by LiveKit Android SDK (RESEARCH §Pitfall 5)
    }
}
rootProject.name = "dAIly"
include(":app")
