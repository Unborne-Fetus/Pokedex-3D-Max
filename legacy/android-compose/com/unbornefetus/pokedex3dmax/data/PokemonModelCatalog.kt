package com.unbornefetus.pokedex3dmax.data

import android.content.Context
import android.net.Uri
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

data class PokemonModel(
    val nationalDexNumber: Int,
    val name: String,
    val formName: String,
    val modelUrl: String,
) {
    val displayName: String
        get() = if (formName.equals("regular", ignoreCase = true)) {
            name
        } else {
            "$name · ${formName.replaceFirstChar { it.uppercase() }}"
        }

    val isOffline: Boolean
        get() = modelUrl.startsWith("file://")
}

object PokemonModelCatalog {
    private const val API_URL = "https://pokemon-3d-api.onrender.com/v1/pokemon"
    private const val PACK_FOLDER = "offline-models"

    suspend fun load(context: Context): List<PokemonModel> = withContext(Dispatchers.IO) {
        findOfflinePack(context)?.let { packRoot ->
            val offline = loadFromOfflinePack(packRoot)
            if (offline.isNotEmpty()) return@withContext offline
        }

        runCatching { loadFromApi() }
            .getOrElse { fallbackRegularModels() }
    }

    private fun findOfflinePack(context: Context): File? {
        val candidates = buildList {
            add(File(context.filesDir, PACK_FOLDER))
            context.getExternalFilesDir(null)?.let { add(File(it, PACK_FOLDER)) }
        }

        return candidates.firstOrNull { File(it, "model_catalog.tsv").isFile }
    }

    private fun loadFromOfflinePack(root: File): List<PokemonModel> {
        val manifest = File(root, "model_catalog.tsv")
        if (!manifest.isFile) return emptyList()

        return manifest.useLines { lines ->
            lines.drop(1).mapNotNull { line ->
                val columns = line.split('\t')
                if (columns.size < 4) return@mapNotNull null

                val dex = columns[0].toIntOrNull() ?: return@mapNotNull null
                val file = File(root, columns[3])
                if (!file.isFile) return@mapNotNull null

                PokemonModel(
                    nationalDexNumber = dex,
                    name = columns[1],
                    formName = columns[2],
                    modelUrl = Uri.fromFile(file).toString(),
                )
            }.toList()
        }
    }

    private fun loadFromApi(): List<PokemonModel> {
        val connection = (URL(API_URL).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 15_000
            readTimeout = 30_000
            setRequestProperty("Accept", "application/json")
            setRequestProperty("User-Agent", "Pokedex-3D-Max-Android")
        }

        try {
            if (connection.responseCode !in 200..299) {
                error("Model API returned HTTP ${connection.responseCode}")
            }

            val body = connection.inputStream.bufferedReader().use { it.readText() }
            val pokemonArray = when {
                body.trimStart().startsWith("[") -> org.json.JSONArray(body)
                else -> {
                    val root = JSONObject(body)
                    when {
                        root.has("pokemon") -> root.getJSONArray("pokemon")
                        root.has("data") -> root.getJSONArray("data")
                        else -> error("Unsupported model catalog JSON shape")
                    }
                }
            }
            val models = ArrayList<PokemonModel>(1400)

            for (pokemonIndex in 0 until pokemonArray.length()) {
                val pokemon = pokemonArray.getJSONObject(pokemonIndex)
                val dexNumber = pokemon.getInt("id")
                val forms = pokemon.getJSONArray("forms")

                for (formIndex in 0 until forms.length()) {
                    val form = forms.getJSONObject(formIndex)
                    val modelUrl = form.optString("model")
                    if (modelUrl.isBlank()) continue

                    models += PokemonModel(
                        nationalDexNumber = dexNumber,
                        name = form.optString("name", "#%04d".format(dexNumber)),
                        formName = form.optString("formName", "regular"),
                        modelUrl = normalizeAssetUrl(modelUrl),
                    )
                }
            }

            return models
                .distinctBy { "${it.nationalDexNumber}|${it.formName}|${it.modelUrl}" }
                .sortedWith(
                    compareBy<PokemonModel> { it.nationalDexNumber }
                        .thenBy { formSortOrder(it.formName) }
                        .thenBy { it.formName },
                )
        } finally {
            connection.disconnect()
        }
    }

    private fun normalizeAssetUrl(url: String): String = url
        .replace("/refs/heads/main/heads/main/", "/refs/heads/main/")
        .replace("/main/heads/main/", "/main/")

    private fun formSortOrder(form: String): Int = when {
        form.equals("regular", ignoreCase = true) -> 0
        form.contains("shiny", ignoreCase = true) -> 2
        else -> 1
    }

    private fun fallbackRegularModels(): List<PokemonModel> {
        return (1..1025).map { dexNumber ->
            PokemonModel(
                nationalDexNumber = dexNumber,
                name = "#%04d".format(dexNumber),
                formName = "regular",
                modelUrl = "https://raw.githubusercontent.com/Pokemon-3D-api/assets/main/models/opt/regular/$dexNumber.glb",
            )
        }
    }
}