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

dependencies {
    implementation(compose.desktop.currentOs)
    implementation(compose.material3)
    implementation("io.github.sceneview:sceneview-compose:4.52.0")
    // sceneview-compose's desktop viewer currently renders glTF but does not
    // advance skeletal animations. Use the same pinned Filament KMP backend
    // directly for the animated desktop viewport.
    implementation("io.github.erkko68.filament:filament-compose:0.6.0")
    implementation("org.json:json:20250517")
}

compose.desktop {
    application {
        mainClass = "com.unbornefetus.pokedex3dmax.desktop.MainKt"
        jvmArgs += "--enable-native-access=ALL-UNNAMED"

        nativeDistributions {
            targetFormats(TargetFormat.Msi, TargetFormat.Exe)
            packageName = "Pokedex 3D Max"
            packageVersion = "0.2.2"

            windows {
                menuGroup = "Pokedex 3D Max"
                upgradeUuid = "78143d6a-bf1d-43b3-b4b3-0e6bdb7f8c87"
            }
        }
    }
}