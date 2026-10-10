plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.unbornefetus.pokedex3dmax"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.unbornefetus.pokedex3dmax"
        minSdk = 26
        targetSdk = 36
        versionCode = 2
        versionName = "0.2.8"
    }

    buildFeatures {
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

// MainActivity renders the shared web experience using Android's WebView.
// Legacy Compose/SceneView sources are retained in legacy/android-compose,
// rather than shipping a duplicate scene engine and unavailable dependencies.
