package com.unbornefetus.pokedex3dmax.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
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
}

object PokemonModelCatalog {
    private const val API_URL = "https://pokemon-3d-api.onrender.com/v1/pokemon"

    suspend fun load(): List<PokemonModel> = withContext(Dispatchers.IO) {
        runCatching { loadFromApi() }
            .getOrElse { fallbackRegularModels() }
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
            val root = JSONObject(body)
            val pokemonArray = root.getJSONArray("pokemon")
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