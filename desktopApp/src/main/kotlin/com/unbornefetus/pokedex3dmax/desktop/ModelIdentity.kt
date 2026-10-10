package com.unbornefetus.pokedex3dmax.desktop

import org.json.JSONObject
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.charset.StandardCharsets
import java.security.MessageDigest

/**
 * Runtime guard shared by all native 3D model selections. Model catalogs and
 * numbered folders are not proof of Pokémon identity; fingerprints of the
 * original exported GLBs are.
 */
internal object ModelIdentity {
    private fun rows(file: String): List<List<String>> =
        ModelIdentity::class.java.getResourceAsStream("/" + file)
            ?.bufferedReader(StandardCharsets.UTF_8)?.use { stream ->
                stream.lineSequence()
                    .filter { it.isNotBlank() && !it.startsWith("#") }
                    .drop(1)
                    .map { it.split('\t') }
                    .toList()
            } ?: emptyList()

    private val provenance: Map<String, Int> by lazy {
        rows("verified_switch_glb_dex.tsv").mapNotNull { row ->
            if (row.size < 2) null
            else row[1].toIntOrNull()?.let { row[0] to it }
        }.toMap()
    }
    private val swshDex: Map<Int, Int> by lazy { dexMap("swsh_model_dex.tsv") }
    private val svDex: Map<Int, Int> by lazy { dexMap("sv_model_dex.tsv") }

    private fun dexMap(file: String): Map<Int, Int> =
        rows(file).mapNotNull { row ->
            if (row.size < 2) null
            else {
                val internal = row[0].toIntOrNull()
                val dex = row[1].toIntOrNull()
                if (internal == null || dex == null) null else internal to dex
            }
        }.toMap()

    private fun actualDex(internal: Int, sourceGame: String?): Int? {
        val game = sourceGame?.lowercase()?.removePrefix("official-game-assets:") ?: return null
        return when {
            game.startsWith("sv") -> if (internal >= 1001)
                svDex[internal] else swshDex[internal] ?: internal
            game.startsWith("swsh") -> swshDex[internal] ?: internal
            (game.startsWith("la") || game.startsWith("za")) && internal in 1001..1007 ->
                svDex[internal]
            else -> internal
        }
    }

    private fun gitBlobSha(bytes: ByteArray): String {
        val digest = MessageDigest.getInstance("SHA-1")
        digest.update(("blob " + bytes.size).toByteArray(StandardCharsets.UTF_8))
        digest.update(0.toByte())
        digest.update(bytes)
        return digest.digest().joinToString("") { "%02x".format(it) }
    }

    private val embeddedIdPattern = Regex(
        """(?:^|[^A-Za-z0-9])pm(\d{4})(?!\d)""", RegexOption.IGNORE_CASE
    )
    private fun embeddedId(bytes: ByteArray): Int? = runCatching {
        if (bytes.size < 24) return@runCatching null
        val header = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
        if (header.getInt(0) != 0x46546C67 || header.getInt(4) != 2
            || header.getInt(8) != bytes.size || header.getInt(16) != 0x4E4F534A) {
            return@runCatching null
        }
        val size = header.getInt(12)
        if (size < 2 || size > 24 * 1024 * 1024 || size > bytes.size - 20)
            return@runCatching null
        val json = JSONObject(String(bytes, 20, size, StandardCharsets.UTF_8))
        for (key in listOf("images", "meshes", "nodes", "materials")) {
            val items = json.optJSONArray(key) ?: continue
            val ids = (0 until items.length()).mapNotNull { index ->
                embeddedIdPattern.find(items.optJSONObject(index)?.optString("name") ?: "")
                    ?.groupValues?.getOrNull(1)?.toIntOrNull()
            }.toSet()
            if (ids.size == 1) return@runCatching ids.single()
            if (ids.size > 1) return@runCatching null
        }
        null
    }.getOrNull()

    fun validate(dex: Int, sourceGame: String?, sourceModelId: Int?, data: ByteArray) {
        require(dex in 1..1025 && data.size >= 24) { "Invalid Pokémon model" }
        val original = provenance[gitBlobSha(data)]
        if (original != null) {
            require(original == dex) {
                "3D file belongs to National #" + original +
                    ", not #" + dex + ". Rebuild the offline model pack."
            }
            return
        }
        val embedded = embeddedId(data)
        if (embedded != null && sourceModelId != null) {
            require(embedded == sourceModelId) {
                "Wrong model: embedded pm" + embedded +
                    " disagrees with catalog pm" + sourceModelId
            }
        }
        val internal = embedded ?: sourceModelId ?: return
        val expected = actualDex(internal, sourceGame)
        if (expected != null) {
            require(expected == dex) {
                "Wrong species: game ID pm" + internal + " is National #" + expected
            }
        } else if (internal >= 1008) {
            error("Unverified game-internal ID pm" + internal +
                  "; reimport the correct original Switch model")
        }
    }

    fun selfTest() {
        check(provenance.size >= 1500)
        check(actualDex(1025, "SV-Poke") == 920)
        check(actualDex(1010, "SV-Poke") == 906)
        check(actualDex(1002, "LA-Poke") == 900)
        check(actualDex(801, "SV-Poke") == 747)
    }
}
