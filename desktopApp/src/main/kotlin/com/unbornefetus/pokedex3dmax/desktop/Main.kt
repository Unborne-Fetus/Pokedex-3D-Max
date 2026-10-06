package com.unbornefetus.pokedex3dmax.desktop

import androidx.compose.foundation.clickable
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
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Window
import androidx.compose.ui.window.application
import androidx.compose.ui.window.rememberWindowState
import io.github.sceneview.compose.ModelSource
import io.github.sceneview.compose.SceneViewer
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths

private data class DesktopModel(
    val dex: Int,
    val name: String,
    val form: String,
    val path: Path,
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
                                Text(
                                    model.form,
                                    style = MaterialTheme.typography.bodySmall,
                                )
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
                        SceneViewer(
                            model = ModelSource.Bytes(it),
                            modifier = Modifier.fillMaxSize(),
                            onError = { error ->
                                System.err.println("3D load failed: " + error.message)
                            },
                        )
                    } ?: Text("Loading " + current.name + "…")
                }
            }
        }
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
        System.getenv("POKEDEX_3D_MAX_MODELS")?.takeIf { it.isNotBlank() }?.let {
            add(Paths.get(it))
        }

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
            val relative = columns[3]

            DesktopModel(
                dex = dex,
                name = columns[1],
                form = columns[2],
                path = root.resolve(relative),
            )
        }
        .filter { Files.isRegularFile(it.path) }
}