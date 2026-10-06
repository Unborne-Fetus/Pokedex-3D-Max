package com.unbornefetus.pokedex3dmax.desktop

import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Window
import androidx.compose.ui.window.application
import androidx.compose.ui.window.rememberWindowState
import dev.romainguy.kotlin.math.Float3
import io.github.sceneview.compose.EnvironmentSource
import io.github.sceneview.compose.Lighting
import io.github.sceneview.compose.ModelSource
import io.github.sceneview.compose.SceneViewer
import io.github.sceneview.compose.rememberUnsavedCameraState
import org.json.JSONObject
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths
import kotlin.math.exp
import kotlin.math.sqrt

private data class DesktopModel(
    val dex: Int,
    val name: String,
    val form: String,
    val path: Path,
)

private data class ModelBounds(
    val center: Float3,
    val radius: Float,
    val maxDimension: Float,
)

fun main() = application {
    Window(
        onCloseRequest = ::exitApplication,
        title = "Pokedex 3D Max",
        state = rememberWindowState(width = 1280.dp, height = 820.dp),
    ) {
        MaterialTheme(colorScheme = darkColorScheme()) {
            DesktopApp()
        }
    }
}

@Composable
private fun DesktopApp() {
    val packRoot = remember { findModelPack() }
    val models = remember(packRoot) { packRoot?.let(::loadManifest).orEmpty() }
    var query by remember { mutableStateOf("") }
    var selected by remember { mutableStateOf<DesktopModel?>(models.firstOrNull()) }

    val filtered = remember(query, models) {
        val q = query.trim().removePrefix("#")
        if (q.isBlank()) {
            models
        } else {
            models.filter {
                it.name.contains(query, ignoreCase = true) ||
                    it.form.contains(query, ignoreCase = true) ||
                    it.dex.toString() == q
            }
        }
    }

    Surface(Modifier.fillMaxSize()) {
        if (packRoot == null) {
            MissingPackScreen()
            return@Surface
        }

        Row(
            modifier = Modifier
                .fillMaxSize()
                .padding(16.dp),
            horizontalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Column(
                modifier = Modifier
                    .width(360.dp)
                    .fillMaxSize(),
            ) {
                Text(
                    "Pokedex 3D Max",
                    style = MaterialTheme.typography.headlineMedium,
                    fontWeight = FontWeight.Bold,
                )
                Text(
                    models.size.toString() + " offline 3D models",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )

                Spacer(Modifier.height(12.dp))

                OutlinedTextField(
                    value = query,
                    onValueChange = { query = it },
                    label = { Text("Search Pokémon, form, or #") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )

                Spacer(Modifier.height(12.dp))

                LazyColumn(
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    items(
                        items = filtered,
                        key = { it.dex.toString() + "|" + it.form + "|" + it.path.toString() },
                    ) { model ->
                        Card(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable { selected = model },
                            colors = CardDefaults.cardColors(
                                containerColor = if (selected == model) {
                                    MaterialTheme.colorScheme.secondaryContainer
                                } else {
                                    MaterialTheme.colorScheme.surfaceContainer
                                },
                            ),
                        ) {
                            Column(Modifier.padding(12.dp)) {
                                Text(
                                    "#%04d  %s".format(model.dex, model.name),
                                    fontWeight = FontWeight.SemiBold,
                                )
                                Text(model.form, style = MaterialTheme.typography.bodySmall)
                            }
                        }
                    }
                }
            }

            Box(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxSize(),
                contentAlignment = Alignment.Center,
            ) {
                val current = selected
                if (current == null) {
                    Text("Choose a Pokémon")
                } else {
                    val bytes by produceState<ByteArray?>(null, current.path) {
                        value = runCatching { Files.readAllBytes(current.path) }.getOrNull()
                    }

                    bytes?.let {
                        PokemonViewport(current, it)
                    } ?: Text("Loading " + current.name + "…")
                }
            }
        }
    }
}

@Composable
private fun PokemonViewport(model: DesktopModel, bytes: ByteArray) {
    key(model.path.toString()) {
        val bounds = remember(bytes) { readModelBounds(bytes) }
        val initialDistance = remember(bounds) {
            maxOf(bounds.radius * 3.0f, bounds.maxDimension * 2.2f, 0.75f)
        }
        val minDistance = remember(bounds) {
            maxOf(bounds.radius * 0.45f, 0.05f)
        }
        val maxDistance = remember(bounds, initialDistance) {
            maxOf(initialDistance * 10f, bounds.radius * 24f, 8f)
        }
        val camera = rememberUnsavedCameraState(
            target = bounds.center,
            distance = initialDistance,
            azimuth = 0f,
            elevation = 8f,
        )

        // Disable SceneView desktop gestures. Its current scroll implementation multiplies
        // distance directly by the raw wheel delta and can jump to an invalid camera state.
        camera.gesturesEnabled = false

        val controls = Modifier
            .pointerInput(camera, minDistance, maxDistance) {
                detectDragGestures { _, drag ->
                    camera.azimuth -= drag.x * 0.28f
                    camera.elevation += drag.y * 0.28f
                }
            }
            .pointerInput(camera, minDistance, maxDistance) {
                awaitPointerEventScope {
                    while (true) {
                        val event = awaitPointerEvent()
                        val scrollY = event.changes.firstOrNull()?.scrollDelta?.y ?: 0f
                        if (scrollY != 0f) {
                            val exponent = (scrollY * 0.10f).coerceIn(-1.0f, 1.0f)
                            val zoomFactor = exp(exponent.toDouble()).toFloat()
                            camera.distance = (camera.distance * zoomFactor)
                                .coerceIn(minDistance, maxDistance)
                        }
                    }
                }
            }

        SceneViewer(
            model = ModelSource.Bytes(bytes),
            modifier = Modifier.fillMaxSize().then(controls),
            camera = camera,
            lighting = Lighting(
                direction = Float3(0.35f, -1.0f, -0.55f),
                intensity = 180_000f,
                ambientIntensity = 1f,
                castShadows = false,
            ),
            environment = EnvironmentSource.Default,
            onError = { error ->
                System.err.println("3D load failed for " + model.name + ": " + error.message)
            },
        )
    }
}

private fun readModelBounds(bytes: ByteArray): ModelBounds {
    return runCatching {
        val buffer = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
        if (buffer.remaining() < 20 || buffer.int != 0x46546C67) {
            error("Not a GLB file")
        }
        val version = buffer.int
        val totalLength = buffer.int
        if (version != 2 || totalLength > bytes.size) {
            error("Unsupported GLB")
        }

        var json: JSONObject? = null
        while (buffer.position() + 8 <= totalLength) {
            val chunkLength = buffer.int
            val chunkType = buffer.int
            if (chunkLength < 0 || buffer.position() + chunkLength > totalLength) break
            val chunk = ByteArray(chunkLength)
            buffer.get(chunk)
            if (chunkType == 0x4E4F534A) {
                val text = String(chunk, StandardCharsets.UTF_8)
                    .trimEnd { it == '\u0000' || it.isWhitespace() }
                json = JSONObject(text)
                break
            }
        }

        val doc = json ?: error("GLB JSON chunk not found")
        val meshes = doc.optJSONArray("meshes") ?: error("No meshes")
        val accessors = doc.optJSONArray("accessors") ?: error("No accessors")
        val positionAccessors = linkedSetOf<Int>()

        for (meshIndex in 0 until meshes.length()) {
            val mesh = meshes.optJSONObject(meshIndex) ?: continue
            val primitives = mesh.optJSONArray("primitives") ?: continue
            for (primitiveIndex in 0 until primitives.length()) {
                val primitive = primitives.optJSONObject(primitiveIndex) ?: continue
                val attributes = primitive.optJSONObject("attributes") ?: continue
                val accessorIndex = attributes.optInt("POSITION", -1)
                if (accessorIndex >= 0) positionAccessors += accessorIndex
            }
        }

        var minX = Float.POSITIVE_INFINITY
        var minY = Float.POSITIVE_INFINITY
        var minZ = Float.POSITIVE_INFINITY
        var maxX = Float.NEGATIVE_INFINITY
        var maxY = Float.NEGATIVE_INFINITY
        var maxZ = Float.NEGATIVE_INFINITY

        for (index in positionAccessors) {
            val accessor = accessors.optJSONObject(index) ?: continue
            val min = accessor.optJSONArray("min") ?: continue
            val max = accessor.optJSONArray("max") ?: continue
            if (min.length() < 3 || max.length() < 3) continue

            minX = minOf(minX, min.optDouble(0).toFloat())
            minY = minOf(minY, min.optDouble(1).toFloat())
            minZ = minOf(minZ, min.optDouble(2).toFloat())
            maxX = maxOf(maxX, max.optDouble(0).toFloat())
            maxY = maxOf(maxY, max.optDouble(1).toFloat())
            maxZ = maxOf(maxZ, max.optDouble(2).toFloat())
        }

        if (!minX.isFinite() || !maxX.isFinite()) error("No POSITION bounds")

        val dx = (maxX - minX).coerceAtLeast(0.001f)
        val dy = (maxY - minY).coerceAtLeast(0.001f)
        val dz = (maxZ - minZ).coerceAtLeast(0.001f)
        ModelBounds(
            center = Float3(
                (minX + maxX) * 0.5f,
                (minY + maxY) * 0.5f,
                (minZ + maxZ) * 0.5f,
            ),
            radius = (sqrt(dx * dx + dy * dy + dz * dz) * 0.5f).coerceAtLeast(0.05f),
            maxDimension = maxOf(dx, dy, dz),
        )
    }.getOrElse {
        ModelBounds(
            center = Float3(0f, 0.5f, 0f),
            radius = 0.75f,
            maxDimension = 1.5f,
        )
    }
}

@Composable
private fun MissingPackScreen() {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(32.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            "Offline model pack not found",
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.Bold,
        )
        Spacer(Modifier.height(12.dp))
        Text(
            "Place the downloaded model pack in ./offline-models, " +
                "%LOCALAPPDATA%\\Pokedex3DMax\\offline-models, or set " +
                "POKEDEX_3D_MAX_MODELS to the pack folder.",
        )
    }
}

private fun findModelPack(): Path? {
    val candidates = buildList {
        System.getenv("POKEDEX_3D_MAX_MODELS")?.takeIf { it.isNotBlank() }?.let { add(Paths.get(it)) }
        add(Paths.get("offline-models").toAbsolutePath())
        System.getenv("LOCALAPPDATA")?.takeIf { it.isNotBlank() }?.let {
            add(Paths.get(it, "Pokedex3DMax", "offline-models"))
        }
        System.getProperty("user.home")?.takeIf { it.isNotBlank() }?.let {
            add(Paths.get(it, "Pokedex3DMax", "offline-models"))
        }
    }
    return candidates.firstOrNull { Files.isRegularFile(it.resolve("model_catalog.tsv")) }
}

private fun loadManifest(root: Path): List<DesktopModel> {
    val manifest = root.resolve("model_catalog.tsv")
    if (!Files.isRegularFile(manifest)) return emptyList()

    return Files.readAllLines(manifest)
        .drop(1)
        .mapNotNull { line ->
            val columns = line.split('\t')
            if (columns.size < 4) return@mapNotNull null
            val dex = columns[0].toIntOrNull() ?: return@mapNotNull null
            DesktopModel(
                dex = dex,
                name = columns[1],
                form = columns[2],
                path = root.resolve(columns[3]),
            )
        }
        .filter { Files.isRegularFile(it.path) }
}