plugins {
    id("com.android.application")
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
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_21
        targetCompatibility = JavaVersion.VERSION_21
    }

    // The web build is the canonical UI/renderer. Android packages the same
    // index.html + web runtime instead of maintaining a second 3D renderer.
    sourceSets {
        getByName("main") {
            assets.srcDir(layout.buildDirectory.dir("generated/pokedexWebAssets"))
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
        // Generated local model packs can be enormous. Keep manifests and the
        // canonical web runtime in the APK; remote/fallback model loading stays
        // identical to index.html.
        exclude("**/*.glb", "**/*.gltf", "**/*.fbx", "**/*.bin")
        exclude("**/*.png", "**/*.jpg", "**/*.jpeg", "**/*.webp", "**/*.ktx2")
    }
}

tasks.named("preBuild").configure {
    dependsOn(syncCanonicalWebAssets)
}

dependencies {
    implementation("androidx.core:core-ktx:1.19.1")
    implementation("androidx.activity:activity-ktx:1.14.0")
}
