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
    implementation("org.graalvm.polyglot:polyglot:24.2.2")
    runtimeOnly("org.graalvm.polyglot:js:24.2.2")
}

compose.desktop {
    application {
        mainClass = "com.unbornefetus.pokedex3dmax.desktop.MainKt"
        jvmArgs += "--enable-native-access=ALL-UNNAMED"

        nativeDistributions {
            modules("jdk.unsupported", "java.management", "java.logging")
            targetFormats(TargetFormat.Msi, TargetFormat.Exe)
            packageName = "Pokedex 3D Max"
            packageVersion = "0.2.7"

            windows {
                menuGroup = "Pokedex 3D Max"
                shortcut = true
                upgradeUuid = "78143d6a-bf1d-43b3-b4b3-0e6bdb7f8c87"
            }
        }
    }
}


// Only battle logic/data are shared. The native EXE never packages index.html.
tasks.processResources {
    // Remove resources left by the previous browser-launcher build.
    doFirst { delete(destinationDir.resolve("shared-web")) }
    from(rootProject.file("web/brisk-engine")) {
        include("browser-engine.js", "data.js")
        into("battle")
    }
}

tasks.register<JavaExec>("verifyDesktop") {
    dependsOn(tasks.classes)
    classpath = sourceSets["main"].runtimeClasspath
    mainClass.set("com.unbornefetus.pokedex3dmax.desktop.MainKt")
    args("--self-test")
}

// Incremental builds may retain the deleted Java launcher class until clean.
tasks.jar {
    exclude("shared-web/**", "**/SharedApp.class")
}

// jpackage refuses an existing image when version/input changes on a rebuild.
tasks.matching { it.name == "createDistributable" }.configureEach {
    doFirst {
        delete(layout.buildDirectory.dir("compose/binaries/main/app/Pokedex 3D Max"))
    }
}
