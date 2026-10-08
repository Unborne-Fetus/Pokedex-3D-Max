package com.unbornefetus.pokedex3dmax.desktop

import org.graalvm.polyglot.Context
import org.graalvm.polyglot.Value
import org.json.JSONObject

/** Runs Brisk battle logic directly, without a browser, DOM, HTTP, or index. */
internal class NativeBattle : AutoCloseable {
    private val context = Context.newBuilder("js")
        .option("engine.WarnInterpreterOnly", "false")
        .build()
    private val engine: Value
    private var room: Value? = null

    init {
        context.eval("js", "var window = {}; var console = {log: function(){}, warn: function(){}, error: function(){}};")
        for (name in listOf("data.js", "browser-engine.js")) {
            val source = requireNotNull(javaClass.getResourceAsStream("/battle/$name")) {
                "Missing bundled battle file: $name"
            }.bufferedReader().use { it.readText() }
            context.eval("js", source)
        }
        engine = context.getBindings("js").getMember("window").getMember("BriskBattleEngine")
        engine.invokeMember("loadData", "unused")
    }

    fun start(team: List<String>, difficulty: String): JSONObject {
        // Parse JSON as guest data; expose no host access to the JS engine.
        val values = context.eval("js", "JSON.parse(" + JSONObject.quote(org.json.JSONArray(team).toString()) + ")")
        room = engine.invokeMember("createBotBattle", values, difficulty)
        return snapshot(engine.invokeMember("snapshot", room))
    }

    fun move(index: Int): JSONObject = snapshot(engine.invokeMember("submitMove", requireNotNull(room), index))
    fun switch(index: Int): JSONObject = snapshot(engine.invokeMember("submitSwitch", requireNotNull(room), index))
    private fun snapshot(value: Value): JSONObject = JSONObject(
        context.eval("js", "(value) => JSON.stringify(value)").execute(value).asString()
    )
    fun nationalDex(species: Int): Int = context.getBindings("js").getMember("window")
        .getMember("BRISK_BATTLE_DATA").getMember("species").getMember(species.toString())
        ?.getMember("nationalDex")?.takeIf { it.fitsInInt() }?.asInt() ?: species
    override fun close() = context.close()
}
