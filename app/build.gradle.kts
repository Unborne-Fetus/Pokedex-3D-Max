plugins {
    id("com.android.application") version "9.4.1"
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "com.unbornefetus.pokedex3dmax"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.unbornefetus.pokedex3dmax"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.0"
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_21
        targetCompatibility = JavaVersion.VERSION_21
    }

    // index.html + web/ are the canonical UI and 3D renderer.
    sourceSets {
        getByName("main") {
            assets.srcDir(layout.buildDirectory.dir("generated/pokedexWebAssets").get().asFile)
        }
    }

    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }
}

val syncCanonicalWebAssets by tasks.registering(Sync::class) {
    into(layout.buildDirectory.dir("generated/pokedexWebAssets"))

    from(rootProject.file("index.html"))
    from(rootProject.file("web")) {
        into("web")
        // Do not accidentally turn generated multi-GB model packs into the APK.
        // The same web runtime still uses its online/fallback sources and manifests.
        exclude("**/*.glb", "**/*.gltf", "**/*.fbx", "**/*.bin")
        exclude("**/*.png", "**/*.jpg", "**/*.jpeg", "**/*.webp", "**/*.ktx2")
    }
}

tasks.named("preBuild").configure {
    dependsOn(syncCanonicalWebAssets)
}

dependencies {
    // Kept temporarily because the retired native Compose/SceneView implementation
    // still exists in source. MainActivity no longer enters that code path.
    val composeBom = platform("androidx.compose:compose-bom:2026.09.00")
    implementation(composeBom)
    implementation("androidx.core:core-ktx:1.19.1")
    implementation("androidx.activity:activity-compose:1.14.0")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.12.0")
    implementation("io.github.sceneview:sceneview:4.34.0")
    debugImplementation("androidx.compose.ui:ui-tooling")
}

