package com.unbornefetus.pokedex3dmax.ui

import androidx.compose.foundation.background
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
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SearchBar
import androidx.compose.material3.SearchBarDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.unbornefetus.pokedex3dmax.data.Pokemon
import com.unbornefetus.pokedex3dmax.data.SamplePokemon

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun Pokedex3DMaxApp() {
    var query by remember { mutableStateOf("") }
    var selected by remember { mutableStateOf<Pokemon?>(null) }

    val visiblePokemon = remember(query) {
        if (query.isBlank()) {
            SamplePokemon.all
        } else {
            SamplePokemon.all.filter {
                it.name.contains(query, ignoreCase = true) ||
                    it.nationalDexNumber.toString() == query.trim()
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
                            "Interactive National Pokédex",
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
            SearchBar(
                inputField = {
                    SearchBarDefaults.InputField(
                        query = query,
                        onQueryChange = { query = it },
                        onSearch = {},
                        expanded = false,
                        onExpandedChange = {},
                        placeholder = { Text("Search Pokémon or #") },
                    )
                },
                expanded = false,
                onExpandedChange = {},
                modifier = Modifier.fillMaxWidth(),
            ) {}

            Spacer(Modifier.height(12.dp))

            selected?.let {
                PokemonPreview(
                    pokemon = it,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(bottom = 12.dp),
                )
            }

            LazyColumn(
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                items(
                    items = visiblePokemon,
                    key = { it.nationalDexNumber to it.formName },
                ) { pokemon ->
                    PokemonRow(
                        pokemon = pokemon,
                        selected = selected == pokemon,
                        onClick = { selected = pokemon },
                    )
                }
            }
        }
    }
}

@Composable
private fun PokemonPreview(
    pokemon: Pokemon,
    modifier: Modifier = Modifier,
) {
    Card(
        modifier = modifier,
        shape = RoundedCornerShape(24.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceContainerHigh,
        ),
    ) {
        Column(modifier = Modifier.padding(20.dp)) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                Box(
                    modifier = Modifier
                        .size(104.dp)
                        .clip(RoundedCornerShape(20.dp))
                        .background(MaterialTheme.colorScheme.surfaceContainerHighest),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        "3D",
                        style = MaterialTheme.typography.headlineLarge,
                        fontWeight = FontWeight.Black,
                    )
                }

                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        "#%04d".format(pokemon.nationalDexNumber),
                        style = MaterialTheme.typography.labelLarge,
                        color = MaterialTheme.colorScheme.primary,
                    )
                    Text(
                        pokemon.name,
                        style = MaterialTheme.typography.headlineMedium,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(pokemon.category)
                    Spacer(Modifier.height(8.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        pokemon.types.forEach { type ->
                            TypeChip(type.displayName)
                        }
                    }
                }
            }

            Spacer(Modifier.height(16.dp))
            HorizontalDivider()
            Spacer(Modifier.height(16.dp))

            Text(
                pokemon.description,
                style = MaterialTheme.typography.bodyLarge,
            )

            Spacer(Modifier.height(12.dp))

            Text(
                "BST ${pokemon.baseStats.total}  •  ${pokemon.heightMeters} m  •  ${pokemon.weightKg} kg",
                style = MaterialTheme.typography.labelLarge,
            )
        }
    }
}

@Composable
private fun PokemonRow(
    pokemon: Pokemon,
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
                .padding(14.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Box(
                modifier = Modifier
                    .size(42.dp)
                    .clip(CircleShape)
                    .background(MaterialTheme.colorScheme.surfaceContainerHighest),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    "%03d".format(pokemon.nationalDexNumber),
                    style = MaterialTheme.typography.labelSmall,
                    fontWeight = FontWeight.Bold,
                )
            }

            Column(modifier = Modifier.weight(1f)) {
                Text(
                    pokemon.name,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                )
                Text(
                    pokemon.types.joinToString(" / ") { it.displayName },
                    style = MaterialTheme.typography.bodySmall,
                )
            }

            Text(
                "Gen ${pokemon.generation}",
                style = MaterialTheme.typography.labelMedium,
            )
        }
    }
}

@Composable
private fun TypeChip(name: String) {
    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(100.dp))
            .background(MaterialTheme.colorScheme.primaryContainer)
            .padding(horizontal = 10.dp, vertical = 5.dp),
    ) {
        Text(
            name,
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onPrimaryContainer,
        )
    }
}
