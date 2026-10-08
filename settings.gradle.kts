pluginManagement {
    repositories {
        mavenCentral()
        google()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
        google()
    }
}

rootProject.name = "Pokedex 3D Max"
// Windows setup invokes only desktop tasks; avoid resolving Android tools there.
val requestedTasks = gradle.startParameter.taskNames
val desktopOnly = requestedTasks.isNotEmpty() && requestedTasks.all { it.startsWith(":desktopApp:") }
if (!desktopOnly) include(":app")
include(":desktopApp")

