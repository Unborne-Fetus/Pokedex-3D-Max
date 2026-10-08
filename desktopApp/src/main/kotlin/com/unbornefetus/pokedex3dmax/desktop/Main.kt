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
import androidx.compose.runtime.SideEffect
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
import io.github.erkko68.filament.compose.FilamentSceneView
import io.github.erkko68.filament.compose.rememberFilamentEngine
import io.github.erkko68.filament.compose.scene.Direction
import io.github.erkko68.filament.compose.scene.DirectionalLight
import io.github.erkko68.filament.compose.scene.GltfInstance
import io.github.erkko68.filament.compose.scene.LightIntensity
import io.github.erkko68.filament.compose.scene.LinearColor
import io.github.erkko68.filament.compose.scene.Position
import io.github.erkko68.filament.compose.scene.Projection
import io.github.erkko68.filament.compose.scene.SkyboxSource
import io.github.erkko68.filament.compose.scene.rememberAnimationState
import io.github.erkko68.filament.compose.scene.rememberCameraState
import io.github.erkko68.filament.compose.scene.rememberGltfAsset
import io.github.erkko68.filament.compose.scene.rememberSkyboxState
import io.github.sceneview.compose.CameraState
import io.github.sceneview.compose.rememberUnsavedCameraState
import org.json.JSONObject
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.exp
import kotlin.math.sin
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
        title = "Pokedex 3D Max v0.2.1",
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
                                Text(prettyFormName(model.form), style = MaterialTheme.typography.bodySmall)
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
        // Match the web index/model-viewer framing: center the real mesh bounds,
        // use a 30-degree FOV, and fit the bounding sphere with a small margin.
        val initialDistance = remember(bounds) {
            val halfFovRadians = (30.0 * PI / 180.0 / 2.0)
            maxOf(
                (bounds.radius / sin(halfFovRadians).toFloat()) * 1.05f,
                0.25f,
            )
        }
        val minDistance = remember(initialDistance) {
            maxOf(initialDistance * 0.12f, 0.03f)
        }
        val maxDistance = remember(initialDistance) {
            maxOf(initialDistance * 10f, 4f)
        }
        val camera = rememberUnsavedCameraState(
            target = bounds.center,
            distance = initialDistance,
            azimuth = 0f,
            elevation = 15f,
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

        AnimatedFilamentViewer(
            model = model,
            bytes = bytes,
            modifier = Modifier.fillMaxSize().then(controls),
            orbitCamera = camera,
        )
    }
}

@Composable
private fun AnimatedFilamentViewer(
    model: DesktopModel,
    bytes: ByteArray,
    modifier: Modifier,
    orbitCamera: CameraState,
) {
    val engine = rememberFilamentEngine()
    var loadError by remember { mutableStateOf<Throwable?>(null) }
    val asset = rememberGltfAsset(
        key = model.path.toString(),
        engine = engine,
        onError = { loadError = it },
    ) { bytes }

    val animationNames = remember(bytes) { readAnimationNames(bytes) }
    val preferredAnimation = remember(animationNames) {
        chooseIdleAnimationIndex(animationNames)
    }
    val animation = rememberAnimationState(
        initialAnimationIndex = preferredAnimation,
        initialCrossFadeDuration = 0f,
        initialLoop = true,
    )
    animation.animationIndex = preferredAnimation
    animation.speed = 1f
    animation.loop = true

    val target = orbitCamera.target
    val camera = rememberCameraState(
        initialEye = orbitEye(
            target,
            orbitCamera.distance,
            orbitCamera.azimuth,
            orbitCamera.elevation,
        ),
        initialTarget = Position(target.x, target.y, target.z),
        initialProjection = Projection.Perspective(fovDegrees = 30.0),
    )
    val skybox = rememberSkyboxState(
        initialSource = SkyboxSource.Color(LinearColor(0.08f, 0.10f, 0.14f)),
    )

    SideEffect {
        val currentTarget = orbitCamera.target
        camera.target = Position(currentTarget.x, currentTarget.y, currentTarget.z)
        camera.eye = orbitEye(
            currentTarget,
            orbitCamera.distance,
            orbitCamera.azimuth,
            orbitCamera.elevation,
        )
    }

    FilamentSceneView(
        modifier = modifier,
        engine = engine,
        cameraState = camera,
        skyboxState = skybox,
    ) {
        DirectionalLight(
            direction = Direction(0.35f, -1.0f, -0.55f),
            intensity = LightIntensity.LuminousPower(180_000f),
        )
        GltfInstance(
            asset = asset,
            animationState = if (preferredAnimation != null) animation else null,
        )
    }

    loadError?.let { error ->
        System.err.println(
            "3D load failed for " + model.name + ": " + (error.message ?: error.toString()),
        )
    }
}


private fun orbitEye(
    center: Float3,
    distance: Float,
    azimuthDegrees: Float,
    elevationDegrees: Float,
): Position {
    val azimuth = azimuthDegrees * (PI / 180.0)
    val elevation = elevationDegrees * (PI / 180.0)
    val horizontal = distance * cos(elevation).toFloat()
    return Position(
        center.x + horizontal * sin(azimuth).toFloat(),
        center.y + distance * sin(elevation).toFloat(),
        center.z + horizontal * cos(azimuth).toFloat(),
    )
}


private fun readAnimationNames(bytes: ByteArray): List<String> = runCatching {
    val buffer = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
    if (buffer.remaining() < 20 || buffer.int != 0x46546C67) return@runCatching emptyList()
    val version = buffer.int
    val totalLength = buffer.int
    if (version != 2 || totalLength > bytes.size) return@runCatching emptyList()

    while (buffer.position() + 8 <= totalLength) {
        val chunkLength = buffer.int
        val chunkType = buffer.int
        if (chunkLength < 0 || buffer.position() + chunkLength > totalLength) break
        val chunk = ByteArray(chunkLength)
        buffer.get(chunk)
        if (chunkType != 0x4E4F534A) continue

        val json = JSONObject(
            String(chunk, StandardCharsets.UTF_8)
                .trimEnd { it == '\u0000' || it.isWhitespace() },
        )
        val animations = json.optJSONArray("animations") ?: return@runCatching emptyList()
        return@runCatching List(animations.length()) { index ->
            animations.optJSONObject(index)?.optString("name")
                ?.takeIf { it.isNotBlank() }
                ?: "animation_" + index
        }
    }
    emptyList()
}.getOrElse { emptyList() }


private fun chooseIdleAnimationIndex(names: List<String>): Int? {
    if (names.isEmpty()) return null

    val preferred = listOf(
        Regex("default(?:idle|wait)", RegexOption.IGNORE_CASE),
        Regex("battle(?:idle|wait)", RegexOption.IGNORE_CASE),
        Regex("(^|[_-])idle([_-]|$)", RegexOption.IGNORE_CASE),
        Regex("wait|stand|breath|rest", RegexOption.IGNORE_CASE),
        Regex("loop", RegexOption.IGNORE_CASE),
    )
    val rejected = Regex(
        "attack|damage|faint|death|down|hit|move|run|walk|jump",
        RegexOption.IGNORE_CASE,
    )

    for (pattern in preferred) {
        val index = names.indexOfFirst {
            pattern.containsMatchIn(it) && !rejected.containsMatchIn(it)
        }
        if (index >= 0) return index
    }

    return names.indexOfFirst { !rejected.containsMatchIn(it) }
        .takeIf { it >= 0 }
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
        // setup/import-switch-models installs validated models here. Prefer it
        // over a possibly stale ./offline-models folder in the launch cwd.
        System.getenv("LOCALAPPDATA")?.takeIf { it.isNotBlank() }?.let {
            add(Paths.get(it, "Pokedex3DMax", "offline-models"))
        }
        add(Paths.get("offline-models").toAbsolutePath())
        System.getProperty("user.home")?.takeIf { it.isNotBlank() }?.let {
            add(Paths.get(it, "Pokedex3DMax", "offline-models"))
        }
    }
    return candidates.firstOrNull { Files.isRegularFile(it.resolve("model_catalog.tsv")) }
}

private fun prettyFormName(raw: String): String {
    val normalized = raw
        .trim()
        .lowercase()
        .replace(Regex("-00$"), "")
    if (normalized.isBlank() || normalized == "regular") return "Regular"

    return normalized
        .replace(Regex("^form-"), "Form ")
        .replace(Regex("^go-form-"), "GO Form ")
        .replace('-', ' ')
        .replace('_', ' ')
        .split(Regex("\\s+"))
        .filter { it.isNotBlank() }
        .joinToString(" ") { token ->
            if (token.all(Char::isDigit)) token
            else token.replaceFirstChar { ch -> ch.uppercase() }
        }
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
        .filter {
            Files.isRegularFile(it.path) &&
                !it.form.contains("shiny", ignoreCase = true) &&
                !it.name.startsWith("Shiny ", ignoreCase = true)
        }
}