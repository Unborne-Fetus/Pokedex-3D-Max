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
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
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
import org.json.JSONArray
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
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
    val idleAnimation: String? = null,
    val idleBreaks: List<String> = emptyList(),
) {
    val stableKey: String
        get() = "%04d|%s|%s".format(dex, form.lowercase(), path.toAbsolutePath().normalize())
}

private data class ModelBounds(
    val center: Float3,
    val radius: Float,
    val maxDimension: Float,
)

fun main(args: Array<String>) {
    if ("--self-test" in args) {
        verifyDesktop()
        return
    }
    launchDesktop()
}

private fun launchDesktop() = application {
    Window(
        onCloseRequest = ::exitApplication,
        title = "Pokedex 3D Max v0.2.7",
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
    // Models are counted from actual local files. Idle clips count only after a model
    // has been instantiated and its animation list checked.
    val modelDexes = remember(models) { models.map { it.dex }.filter { it in 1..1025 }.toSet() }
    var inspectedAnimationDex by remember(models) { mutableStateOf(emptySet<Int>()) }
    var confirmedAnimationDex by remember(models) { mutableStateOf(emptySet<Int>()) }
    val modelCount = modelDexes.size
    val checkedCount = inspectedAnimationDex.count { it in modelDexes }
    val animationCount = confirmedAnimationDex.count { it in modelDexes }
    var rotate by remember { mutableStateOf(false) }
    var breaks by remember { mutableStateOf(true) }
    var reset by remember { mutableStateOf(0) }
    var query by remember { mutableStateOf("") }
    var selectedKey by remember(models) {
        mutableStateOf(models.firstOrNull()?.stableKey)
    }

    val selected = remember(models, selectedKey) {
        selectedKey?.let { key -> models.firstOrNull { it.stableKey == key } }
            ?: models.firstOrNull()
    }

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
        Column(Modifier.fillMaxSize()) {
        if (packRoot == null) {
            MissingPackScreen()
            return@Column
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
                    models.size.toString() + " models · " + models.count { it.path.toString().replace('\\', '/').contains("/switch/") } + " Switch",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )

                Spacer(Modifier.height(12.dp))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text("3D models", fontWeight = FontWeight.SemiBold)
                    Text("$modelCount / 1,025")
                }
                LinearProgressIndicator(
                    progress = { modelCount / 1025f },
                    modifier = Modifier.fillMaxWidth(),
                    color = MaterialTheme.colorScheme.primary,
                )
                Text(
                    "%.1f%% · %d model files missing".format(modelCount * 100.0 / 1025, 1025 - modelCount),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )

                Spacer(Modifier.height(10.dp))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text("Idle animations", fontWeight = FontWeight.SemiBold)
                    Text("$animationCount / 1,025")
                }
                LinearProgressIndicator(
                    progress = { animationCount / 1025f },
                    modifier = Modifier.fillMaxWidth(),
                    color = MaterialTheme.colorScheme.tertiary,
                )
                Text(
                    "%.1f%% · %d inspected; others not yet verified".format(
                        animationCount * 100.0 / 1025, checkedCount,
                    ),
                    style = MaterialTheme.typography.bodySmall,
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
                        items = filtered.distinctBy { it.dex },
                        key = { it.dex.toString() + "|" + it.form + "|" + it.path.toString() },
                    ) { model ->
                        Card(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable { selectedKey = model.stableKey },
                            colors = CardDefaults.cardColors(
                                containerColor = if (selected?.dex == model.dex) {
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
                                Text(prettyFormName(model.form, model.dex), style = MaterialTheme.typography.bodySmall)
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
                    key(current.stableKey) {
                        val bytes by produceState<ByteArray?>(null, current.stableKey) {
                            value = withContext(Dispatchers.IO) { runCatching { Files.readAllBytes(current.path) }.getOrNull() }
                        }

                        Column(Modifier.fillMaxSize()) {
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                Text("#%04d %s".format(current.dex, current.name), style = MaterialTheme.typography.headlineMedium)
                                Box {
                                    var open by remember { mutableStateOf(false) }
                                    Button(onClick = { open = true }) { Text(prettyFormName(current.form, current.dex)) }
                                    DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
                                        for (form in models.filter { it.dex == current.dex }) {
                                            DropdownMenuItem(text = { Text(prettyFormName(form.form, form.dex)) },
                                                onClick = { selectedKey = form.stableKey; open = false })
                                        }
                                    }
                                }
                            }
                            Box(Modifier.weight(1f).fillMaxWidth()) {
                                bytes?.let {
                                    PokemonViewport(current, it, rotate, breaks, reset) { dex, hasIdle ->
                                        inspectedAnimationDex = inspectedAnimationDex + dex
                                        if (hasIdle) confirmedAnimationDex = confirmedAnimationDex + dex
                                        else confirmedAnimationDex = confirmedAnimationDex - dex
                                    }
                                } ?: Text("Loading " + current.name + "…")
                            }
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                Button(onClick = { reset++ }) { Text("Reset camera") }
                                Button(onClick = { rotate = !rotate }) { Text("Auto-rotate: " + if (rotate) "On" else "Off") }
                                Button(onClick = { breaks = !breaks }) { Text("Idle breaks: " + if (breaks) "On" else "Off") }
                            }
                        }
                    }
                }
            }
        }
        }
    }
}

@Composable
private fun PokemonViewport(
    model: DesktopModel, bytes: ByteArray, rotate: Boolean, breaks: Boolean, reset: Int,
    onAnimationInspected: (Int, Boolean) -> Unit,
) {
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
            azimuth = 20f,
            elevation = 25f,
        )

        LaunchedEffect(reset) {
            camera.azimuth = 20f
            camera.elevation = 25f
            camera.target = bounds.center
            camera.distance = initialDistance
        }
        LaunchedEffect(rotate) {
            while (rotate) {
                delay(16)
                camera.azimuth += 0.24f
            }
        }

        // Disable SceneView desktop gestures. Its current scroll implementation multiplies
        // distance directly by the raw wheel delta and can jump to an invalid camera state.
        camera.gesturesEnabled = false

        val controls = Modifier
            .pointerInput(camera, minDistance, maxDistance) {
                detectDragGestures { _, drag ->
                    camera.azimuth -= drag.x * 0.28f
                    camera.elevation = (camera.elevation + drag.y * 0.28f).coerceIn(-89f, 89f)
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
            breaksEnabled = breaks,
            onAnimationInspected = onAnimationInspected,
        )
    }
}

@Composable
private fun AnimatedFilamentViewer(
    model: DesktopModel,
    bytes: ByteArray,
    modifier: Modifier,
    orbitCamera: CameraState,
    breaksEnabled: Boolean,
    onAnimationInspected: (Int, Boolean) -> Unit,
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
        model.idleAnimation?.let { animationNames.indexOf(it).takeIf { i -> i >= 0 } }
            ?: chooseIdleAnimationIndex(animationNames)
    }
    val animation = rememberAnimationState(
        initialAnimationIndex = preferredAnimation,
        initialCrossFadeDuration = 0f,
        initialLoop = true,
    )
    LaunchedEffect(preferredAnimation, breaksEnabled) {
        animation.animationIndex = preferredAnimation
        animation.speed = 1f
        animation.loop = true
        val clips = model.idleBreaks.mapNotNull { name ->
            animationNames.indexOf(name).takeIf { it >= 0 && it != preferredAnimation }
        }
        var next = 0
        while (breaksEnabled && clips.isNotEmpty()) {
            delay(12000)
            val clip = clips[next++ % clips.size]
            animation.animationIndex = clip
            animation.loop = false
            delay(readAnimationDuration(bytes, clip))
            animation.animationIndex = preferredAnimation
            animation.loop = true
        }
    }

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
            onCreate = {
                // Filament KMP 0.6 exposes the instance bounds as a Box with
                // center/halfExtent properties. Use those transformed bounds
                // directly so the camera starts centered on the rendered model.
                val box = instance.boundingBox
                val center = box.center
                val extent = box.halfExtent

                if (
                    center.size >= 3 &&
                    extent.size >= 3 &&
                    center.all { it.isFinite() } &&
                    extent.all { it.isFinite() } &&
                    extent.any { it > 0f }
                ) {
                    val fittedTarget = Float3(center[0], center[1], center[2])
                    val radius = sqrt(
                        extent[0] * extent[0] +
                            extent[1] * extent[1] +
                            extent[2] * extent[2],
                    ).coerceAtLeast(0.05f)
                    val halfFovRadians = (30.0 * PI / 180.0 / 2.0)
                    val fittedDistance = maxOf(
                        (radius / sin(halfFovRadians).toFloat()) * 1.05f,
                        0.25f,
                    )

                    orbitCamera.target = fittedTarget
                    orbitCamera.distance = fittedDistance
                    orbitCamera.azimuth = 20f
                    orbitCamera.elevation = 25f

                    camera.target = Position(
                        fittedTarget.x,
                        fittedTarget.y,
                        fittedTarget.z,
                    )
                    camera.eye = orbitEye(
                        fittedTarget,
                        fittedDistance,
                        20f,
                        25f,
                    )
                }
                onAnimationInspected(model.dex, preferredAnimation != null)
            },
        )
    }

    loadError?.let { error ->
        Text("Could not load " + model.name + ": " + (error.message ?: "invalid model"))
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


private fun readAnimationDuration(bytes: ByteArray, index: Int): Long = runCatching {
    val buffer = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
    buffer.position(12)
    val length = buffer.int
    require(buffer.int == 0x4E4F534A && length <= buffer.remaining())
    val text = ByteArray(length).also { buffer.get(it) }
    val doc = JSONObject(String(text, StandardCharsets.UTF_8).trimEnd { it == '\u0000' || it.isWhitespace() })
    val samplers = doc.getJSONArray("animations").getJSONObject(index).getJSONArray("samplers")
    val accessors = doc.getJSONArray("accessors")
    var seconds = 0.0
    for (i in 0 until samplers.length()) {
        val accessor = accessors.getJSONObject(samplers.getJSONObject(i).getInt("input"))
        seconds = maxOf(seconds, accessor.optJSONArray("max")?.optDouble(0, 0.0) ?: 0.0)
    }
    require(seconds.isFinite() && seconds > 0.0)
    (seconds * 1000).toLong().coerceIn(100, 60000)
}.getOrDefault(3000L)


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
        "attack|damage|faint|death|down|hit|move|run|walk|jump|bind|t[-_ ]?pose",
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

private fun prettyFormName(raw: String, dex: Int? = null): String {
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


private fun loadSpeciesNames(root: Path): Map<Int, String> {
    val path = root.resolve("species_names.tsv")
    if (!Files.isRegularFile(path)) return emptyMap()

    return Files.readAllLines(path)
        .drop(1)
        .mapNotNull { line ->
            val columns = line.split('\t')
            if (columns.size < 2) return@mapNotNull null
            val dex = columns[0].toIntOrNull() ?: return@mapNotNull null
            val name = columns[1].trim()
            if (name.isBlank() || name.startsWith("#")) return@mapNotNull null
            dex to name
        }
        .toMap()
}



private fun loadManifest(root: Path): List<DesktopModel> {
    val manifest = root.resolve("model_catalog.tsv")
    if (!Files.isRegularFile(manifest)) return emptyList()

    val speciesNames = loadSpeciesNames(root)
    val metadata = runCatching {
        JSONArray(Files.readString(root.resolve("switch-model-metadata.json")))
    }.getOrDefault(JSONArray())
    val byKey = (0 until metadata.length()).associate { i ->
        val entry = metadata.getJSONObject(i)
        (entry.getInt("dex") to entry.getString("form")) to entry
    }
    val absoluteRoot = root.toAbsolutePath().normalize()

    return Files.readAllLines(manifest)
        .drop(1)
        .mapNotNull { line ->
            val columns = line.split('\t')
            if (columns.size < 4) return@mapNotNull null
            val dex = columns[0].toIntOrNull() ?: return@mapNotNull null
            val rawName = columns[1].trim()
            val path = absoluteRoot.resolve(columns[3].replace('\\', '/')).normalize()
            if (!path.startsWith(absoluteRoot) || !Files.isRegularFile(path) ||
                !path.toRealPath().startsWith(absoluteRoot.toRealPath())) return@mapNotNull null
            val entry = byKey[dex to columns[2]]
            val isSwitch = absoluteRoot.relativize(path).toString().replace('\\', '/').startsWith("switch/")
            if (!isSwitch) return@mapNotNull null
            if (isSwitch && entry?.optBoolean("ready", true) == false) return@mapNotNull null
            DesktopModel(
                dex = dex,
                name = speciesNames[dex]
                    ?: rawName.ifBlank { "#%04d".format(dex) },
                form = columns[2],
                path = path,
                idleAnimation = if (isSwitch) entry?.optString("idleAnimation")?.takeIf { it.isNotBlank() } else null,
                idleBreaks = if (isSwitch) entry?.optJSONArray("idleBreaks")?.let { clips ->
                    List(clips.length()) { clips.getString(it) }
                }.orEmpty() else emptyList(),
            )
        }
        .filter {
            Files.isRegularFile(it.path) &&
                it.form.equals("regular", ignoreCase = true)
        }
        .distinctBy { it.dex }
        .sortedBy { it.dex }
}

/** Headless checks exercise the regular Switch-only desktop catalog. */
private fun verifyDesktop() {
    val root = Files.createTempDirectory("pokedex-native-check")
    try {
        for (path in listOf("old/regular.glb", "switch/0006/regular.glb", "switch/0006/form-51-00.glb")) {
            val file = root.resolve(path)
            Files.createDirectories(file.parent)
            Files.write(file, byteArrayOf(1))
        }
        Files.writeString(root.resolve("model_catalog.tsv"),
            "dex\tname\tform\tpath\n" +
            "6\tCharizard\tregular\told/regular.glb\n" +
            "6\tCharizard\tregular\tswitch/0006/regular.glb\n" +
            "6\tCharizard\tform-51-00\tswitch/0006/form-51-00.glb\n" +
            "7\tOutside\tregular\t../outside.glb\n")
        val models = loadManifest(root)
        check(models.size == 1)
        check(models.single().dex == 6)
        check(models.single().form.equals("regular", ignoreCase = true))
        check(models.single().path == root.resolve("switch/0006/regular.glb"))
        check(chooseIdleAnimationIndex(listOf("attack", "defaultwait", "damage")) == 1)
        check(chooseIdleAnimationIndex(listOf("attack", "damage")) == null)
        Files.writeString(root.resolve("switch-model-metadata.json"),
            "[{\"dex\":6,\"form\":\"regular\",\"ready\":false}]")
        check(loadManifest(root).isEmpty())
    } finally {
        Files.walk(root).use { paths -> paths.sorted(Comparator.reverseOrder()).forEach { Files.deleteIfExists(it) } }
    }
    println("Native desktop checks passed: regular Switch-only catalog, path containment and idle selection.")
}
