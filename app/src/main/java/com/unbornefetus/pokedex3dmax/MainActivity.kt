package com.unbornefetus.pokedex3dmax

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.unbornefetus.pokedex3dmax.ui.Pokedex3DMaxApp
import com.unbornefetus.pokedex3dmax.ui.theme.Pokedex3DMaxTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        setContent {
            Pokedex3DMaxTheme {
                Pokedex3DMaxApp()
            }
        }
    }
}
