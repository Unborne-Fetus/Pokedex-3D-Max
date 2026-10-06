package com.unbornefetus.pokedex3dmax.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SearchBar
import androidx.compose.material3.SearchBarDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.unbornefetus.pokedex3dmax.data.PokemonModel
import com.unbornefetus.pokedex3dmax.data.PokemonModelCatalog

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun Pokedex3DMaxApp() {
    var query by remember { mutableStateOf("") }
    var models by remember { mutableStateOf<List<PokemonModel>>(emptyList()) }
    var selected by remember { mutableStateOf<PokemonModel?>(null) }
    var loading by remember { mutableStateOf(true) }

    LaunchedEffect(Unit) {
        models = PokemonModelCatalog.load()
        selected = models.firstOrNull()
        loading = false
    }

    val visibleModels = remember(query, models) {
        val cleaned = query.trim().removePrefix("#")
        if (cleaned.isBlank()) {
            models
        } else {
            models.filter { model ->
                model.name.contains(query, ignoreCase = true) ||
                    model.formName.contains(query, ignoreCase = true) ||
                    model.nationalDexNumber.toString() == cleaned
            }
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("Pokedex 3D Max", fontWeight = FontWeight.Bold)
                        Text(
                            if (loading) "Loading 3D model catalog…" else "${models.size} 3D models available",
                            style = MaterialTheme.typography.labelMedium,
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.surface,
                ),
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 16.dp),
        ) {
            selected?.let { model ->
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(330.dp),
                    shape = RoundedCornerShape(24.dp),
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.surfaceContainerHigh,
                    ),
                ) {
                    PokemonModelViewer(
                        model = model,
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(8.dp),
                    )
                }

                Spacer(Modifier.height(8.dp))
                Text(
                    "#%04d  %s".format(model.nationalDexNumber, model.displayName),
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                )
                Text(
                    "Drag to rotate · Pinch to zoom · Animations play automatically",
                    style = MaterialTheme.typography.bodySmall,
                )
                Spacer(Modifier.height(10.dp))
            }

            SearchBar(
                inputField = {
                    SearchBarDefaults.InputField(
                        query = query,
                        onQueryChange = { query = it },
                        onSearch = {},
                        expanded = false,
                        onExpandedChange = {},
                        placeholder = { Text("Search Pokémon, form, or #") },
                    )
                },
                expanded = false,
                onExpandedChange = {},
                modifier = Modifier.fillMaxWidth(),
            ) {}

            Spacer(Modifier.height(10.dp))

            if (loading) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(32.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    CircularProgressIndicator()
                    Spacer(Modifier.height(12.dp))
                    Text("Loading the 3D model library…")
                }
            } else {
                LazyColumn(
                    verticalArrangement = Arrangement.spacedBy(7.dp),
                ) {
                    items(
                        items = visibleModels,
                        key = { "${it.nationalDexNumber}|${it.formName}|${it.modelUrl}" },
                    ) { model ->
                        ModelRow(
                            model = model,
                            selected = selected == model,
                            onClick = { selected = model },
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun ModelRow(
    model: PokemonModel,
    selected: Boolean,
    onClick: () -> Unit,
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
        colors = CardDefaults.cardColors(
            containerColor = if (selected) {
                MaterialTheme.colorScheme.secondaryContainer
            } else {
                MaterialTheme.colorScheme.surfaceContainer
            },
        ),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 14.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                "#%04d".format(model.nationalDexNumber),
                style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.primary,
            )

            Column(modifier = Modifier.weight(1f)) {
                Text(
                    model.name,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                )
                Text(
                    model.formName.replaceFirstChar { it.uppercase() },
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }
    }
}