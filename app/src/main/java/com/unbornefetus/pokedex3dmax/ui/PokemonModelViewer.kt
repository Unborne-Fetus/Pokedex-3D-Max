package com.unbornefetus.pokedex3dmax.ui

import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.key
import androidx.compose.ui.Modifier
import com.unbornefetus.pokedex3dmax.data.PokemonModel
import io.github.sceneview.SceneView
import io.github.sceneview.node.ModelNode
import io.github.sceneview.rememberModelInstance

@Composable
fun PokemonModelViewer(
    model: PokemonModel,
    modifier: Modifier = Modifier,
) {
    key(model.modelUrl) {
        SceneView(
            modifier = modifier.fillMaxSize(),
        ) {
            rememberModelInstance(
                modelLoader = modelLoader,
                fileLocation = model.modelUrl,
            )?.let { instance ->
                ModelNode(
                    modelInstance = instance,
                    scaleToUnits = 1.0f,
                    autoAnimate = true,
                )
            }
        }
    }
}