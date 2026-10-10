package com.unbornefetus.pokedex3dmax.data

data class Pokemon(
    val nationalDexNumber: Int,
    val name: String,
    val category: String,
    val generation: Int,
    val types: List<PokemonType>,
    val formName: String? = null,
    val heightMeters: Double,
    val weightKg: Double,
    val baseStats: BaseStats,
    val abilities: List<String>,
    val hiddenAbility: String? = null,
    val description: String,
)

data class BaseStats(
    val hp: Int,
    val attack: Int,
    val defense: Int,
    val specialAttack: Int,
    val specialDefense: Int,
    val speed: Int,
) {
    val total: Int
        get() = hp + attack + defense + specialAttack + specialDefense + speed
}

enum class PokemonType(val displayName: String) {
    NORMAL("Normal"),
    FIRE("Fire"),
    WATER("Water"),
    ELECTRIC("Electric"),
    GRASS("Grass"),
    ICE("Ice"),
    FIGHTING("Fighting"),
    POISON("Poison"),
    GROUND("Ground"),
    FLYING("Flying"),
    PSYCHIC("Psychic"),
    BUG("Bug"),
    ROCK("Rock"),
    GHOST("Ghost"),
    DRAGON("Dragon"),
    DARK("Dark"),
    STEEL("Steel"),
    FAIRY("Fairy"),
}
