import org.jetbrains.compose.desktop.application.dsl.TargetFormat
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("org.jetbrains.kotlin.jvm")
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.compose")
}

kotlin {
    jvmToolchain(22)
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_22)
    }
}

// Package the same files used by index.html. Downloaded packs remain external.
tasks.processResources {
    from(rootProject.projectDir) {
        include("index.html", "web/**")
        exclude("web/models/**", "web/brisk-engine/source/**")
        into("shared-web")
    }
    from(rootProject.file("web/models")) {
        include("*.js", "*.json")
        into("shared-web/web/models")
    }
}

compose.desktop {
    application {
        mainClass = "com.unbornefetus.pokedex3dmax.desktop.SharedApp"

        nativeDistributions {
            modules("jdk.httpserver", "java.desktop")
            targetFormats(TargetFormat.Msi, TargetFormat.Exe)
            packageName = "Pokedex 3D Max"
            packageVersion = "0.2.5"

            windows {
                menuGroup = "Pokedex 3D Max"
                shortcut = true
                upgradeUuid = "78143d6a-bf1d-43b3-b4b3-0e6bdb7f8c87"
            }
        }
    }
}
