# Candidate GLB inspection: 122 missing Pokémon

Source: [pokemon-party/3d-pokemon — models/opt/regular](https://github.com/pokemon-party/3d-pokemon/tree/main/models/opt/regular)

Audit: [GitHub Actions run 38027082807](https://github.com/Unborne-Fetus/Pokedex-3D-Max/actions/runs/38027082807), completed October 9, 2026 (Pacific time). The workflow ran `scripts/audit_pokemon_party_glbs.py`, downloaded and structurally inspected the actual public GLB bytes, and uploaded full JSON/TSV reports as the `pokemon-party-candidate-audit` artifact.

## Result

- **122** Pokémon on the user-reported missing list.
- **109** species represented by **111 GLBs**. Pyroar and Oinkologne each use male/female GLB variants.
- **13** species not represented by their regular-folder filenames.
- **17** species have a structurally readable GLB with embedded base-color textures for every used material and animation channels with an identifiable named idle.
- **20** species' candidate GLBs have partial or absent embedded base-color texture coverage (five of these also have named idle animations).
- **72** species have texture-complete candidates but no identifiable named idle: some have no animation clips and some have ambiguous animations.
- **No** files failed to download or parse during this audit.

### What these checks do and do not establish

A complete material binding does not prove that original Pokémon texture colors, UV transforms, opacity and shader behavior render correctly. A named idle with glTF channel/sampler data does not prove that animation motion, skinning, orientation or camera framing looks correct. Model size/scale and positioning require actual visual inspection. Draco-compressed candidates also require a compatible GLB renderer.

**Permission was not verified for any individual model.** This external repository's MIT license covers its software; its README explicitly attributes the underlying Pokémon assets to Nintendo, Creatures and Game Freak, and Sketchfab source licenses may vary. Do not assume that MIT grants permission to republish the GLBs.

The results are a candidate audit, **not** proof that 109 imports are safe, not a deployment, and not an update to the Finished Pokémon count. No Pokémon in the existing Switch pack was replaced.

## Per-Pokémon results

| National Dex | Pokémon | GLB candidate | Embedded base-color materials | Embedded animation |
|---|---|---|---|---|
| #0165 | Ledyba | 165.glb | Partial | No valid animations |
| #0166 | Ledian | 166.glb | Partial | No valid animations |
| #0201 | Unown | 201.glb | No base-color textures | No valid animations |
| #0276 | Taillow | 276.glb | Complete binding | No valid animations |
| #0277 | Swellow | 277.glb | Complete binding | No valid animations |
| #0300 | Skitty | 300.glb | Complete binding | No valid animations |
| #0301 | Delcatty | 301.glb | Complete binding | No valid animations |
| #0327 | Spinda | 327.glb | Complete binding | No valid animations |
| #0351 | Castform | 351.glb | Complete binding | No valid animations |
| #0366 | Clamperl | 366.glb | Complete binding | No valid animations |
| #0367 | Huntail | 367.glb | Complete binding | No valid animations |
| #0368 | Gorebyss | 368.glb | Complete binding | No valid animations |
| #0386 | Deoxys | 386.glb | Complete binding | Animated, idle uncertain |
| #0412 | Burmy | 412.glb | Complete binding | No valid animations |
| #0413 | Wormadam | 413.glb | Complete binding | No valid animations |
| #0421 | Cherrim | 421.glb | Complete binding | No valid animations |
| #0422 | Shellos | 422.glb | Complete binding | No valid animations |
| #0423 | Gastrodon | 423.glb | Complete binding | No valid animations |
| #0479 | Rotom | 479.glb | Complete binding | No valid animations |
| #0487 | Giratina | 487.glb | Complete binding | No valid animations |
| #0492 | Shaymin | 492.glb | Complete binding | No valid animations |
| #0493 | Arceus | 493.glb | Complete binding | No valid animations |
| #0550 | Basculin | 550.glb | Complete binding | No valid animations |
| #0555 | Darmanitan | 555.glb | Complete binding | No valid animations |
| #0585 | Deerling | 585.glb | Complete binding | No valid animations |
| #0586 | Sawsbuck | 586.glb | Complete binding | No valid animations |
| #0641 | Tornadus | 641.glb | Complete binding | No valid animations |
| #0642 | Thundurus | 642.glb | Complete binding | No valid animations |
| #0645 | Landorus | 645.glb | Complete binding | Named idle present |
| #0646 | Kyurem | 646.glb | Partial | No valid animations |
| #0647 | Keldeo | 647.glb | Complete binding | No valid animations |
| #0648 | Meloetta | 648.glb | Complete binding | No valid animations |
| #0649 | Genesect | 649.glb | Complete binding | No valid animations |
| #0650 | Chespin | 650.glb | Complete binding | No valid animations |
| #0651 | Quilladin | 651.glb | Complete binding | No valid animations |
| #0652 | Chesnaught | 652.glb | Complete binding | No valid animations |
| #0653 | Fennekin | 653.glb | Complete binding | No valid animations |
| #0654 | Braixen | 654.glb | Complete binding | No valid animations |
| #0655 | Delphox | 655.glb | Complete binding | No valid animations |
| #0656 | Froakie | 656.glb | Complete binding | No valid animations |
| #0657 | Frogadier | 657.glb | Complete binding | No valid animations |
| #0658 | Greninja | 658.glb | Partial | Named idle present |
| #0664 | Scatterbug | 664.glb | Complete binding | No valid animations |
| #0665 | Spewpa | 665.glb | Partial | No valid animations |
| #0666 | Vivillon | 666.glb | Complete binding | No valid animations |
| #0667 | Litleo | 667.glb | Partial | No valid animations |
| #0668 | Pyroar | 668-F.glb, 668-M.glb | Complete binding | No valid animations |
| #0669 | Flabébé | 669.glb | Complete binding | No valid animations |
| #0670 | Floette | 670.glb | Complete binding | No valid animations |
| #0671 | Florges | 671.glb | Complete binding | No valid animations |
| #0672 | Skiddo | 672.glb | Complete binding | No valid animations |
| #0673 | Gogoat | 673.glb | Complete binding | No valid animations |
| #0676 | Furfrou | 676.glb | Partial | No valid animations |
| #0681 | Aegislash | 681.glb | Complete binding | No valid animations |
| #0735 | Gumshoos | 735.glb | Complete binding | No valid animations |
| #0746 | Wishiwashi | 746.glb | Complete binding | No valid animations |
| #0774 | Minior | 774.glb | Complete binding | No valid animations |
| #0775 | Komala | 775.glb | Complete binding | No valid animations |
| #0778 | Mimikyu | 778.glb | Complete binding | Animated, idle uncertain |
| #0779 | Bruxish | 779.glb | Partial | No valid animations |
| #0854 | Sinistea | — | **Not found** | — |
| #0862 | Obstagoon | 862.glb | Partial | Animated, idle uncertain |
| #0864 | Cursola | — | **Not found** | — |
| #0865 | Sirfetch’d | 865.glb | Complete binding | No valid animations |
| #0875 | Eiscue | 875.glb | Partial | Named idle present |
| #0877 | Morpeko | 877.glb | Complete binding | No valid animations |
| #0889 | Zamazenta | 889.glb | Complete binding | No valid animations |
| #0893 | Zarude | 893.glb | Partial | Named idle present |
| #0898 | Calyrex | 898.glb | Complete binding | No valid animations |
| #0899 | Wyrdeer | 899.glb | Complete binding | Named idle present |
| #0900 | Kleavor | 900.glb | Complete binding | Named idle present |
| #0905 | Enamorus | 905.glb | Complete binding | Named idle present |
| #0906 | Sprigatito | 906.glb | Complete binding | No valid animations |
| #0907 | Floragato | 907.glb | No base-color textures | No valid animations |
| #0908 | Meowscarada | 908.glb | Partial | No valid animations |
| #0911 | Skeledirge | 911.glb | Complete binding | Named idle present |
| #0912 | Quaxly | 912.glb | Complete binding | No valid animations |
| #0915 | Lechonk | 915.glb | Partial | No valid animations |
| #0916 | Oinkologne | 916-F.glb, 916-M.glb | Complete binding | Named idle present |
| #0917 | Tarountula | 917.glb | Complete binding | No valid animations |
| #0922 | Pawmo | 922.glb | Complete binding | Animated, idle uncertain |
| #0925 | Maushold | 925.glb | Complete binding | No valid animations |
| #0928 | Smoliv | 928.glb | Complete binding | No valid animations |
| #0930 | Arboliva | 930.glb | Complete binding | No valid animations |
| #0931 | Squawkabilly | — | **Not found** | — |
| #0932 | Nacli | 932.glb | Partial | Named idle present |
| #0938 | Tadbulb | — | **Not found** | — |
| #0939 | Bellibolt | — | **Not found** | — |
| #0941 | Kilowattrel | 941.glb | Complete binding | Named idle present |
| #0943 | Mabosstiff | 943.glb | Complete binding | No valid animations |
| #0947 | Brambleghast | 947.glb | Complete binding | Named idle present |
| #0960 | Wiglett | 960.glb | Complete binding | No valid animations |
| #0961 | Wugtrio | — | **Not found** | — |
| #0962 | Bombirdier | 962.glb | Complete binding | Animated, idle uncertain |
| #0963 | Finizen | — | **Not found** | — |
| #0972 | Houndstone | — | **Not found** | — |
| #0973 | Flamigo | 973.glb | Complete binding | No valid animations |
| #0975 | Cetitan | 975.glb | Complete binding | No valid animations |
| #0979 | Annihilape | 979.glb | Partial | Named idle present |
| #0980 | Clodsire | 980.glb | Partial | No valid animations |
| #0981 | Farigiraf | 981.glb | Complete binding | Named idle present |
| #0983 | Kingambit | 983.glb | Complete binding | Named idle present |
| #0986 | Brute Bonnet | — | **Not found** | — |
| #0987 | Flutter Mane | 987.glb | Complete binding | Named idle present |
| #0988 | Slither Wing | — | **Not found** | — |
| #0991 | Iron Bundle | — | **Not found** | — |
| #0992 | Iron Hands | — | **Not found** | — |
| #0993 | Iron Jugulis | — | **Not found** | — |
| #0994 | Iron Moth | 994.glb | Complete binding | Named idle present |
| #0995 | Iron Thorns | 995.glb | Complete binding | Named idle present |
| #0996 | Frigibax | 996.glb | Complete binding | Animated, idle uncertain |
| #0997 | Arctibax | 997.glb | Complete binding | Animated, idle uncertain |
| #0998 | Baxcalibur | 998.glb | Complete binding | Animated, idle uncertain |
| #0999 | Gimmighoul | 999.glb | Complete binding | Named idle present |
| #1000 | Gholdengo | 1000.glb | Complete binding | Named idle present |
| #1003 | Ting-Lu | 1003.glb | Complete binding | Named idle present |
| #1004 | Chi-Yu | 1004.glb | Complete binding | Named idle present |
| #1005 | Roaring Moon | 1005.glb | Complete binding | No valid animations |
| #1006 | Iron Valiant | 1006.glb | Partial | No valid animations |
| #1008 | Miraidon | 1008.glb | Complete binding | Animated, idle uncertain |
| #1009 | Walking Wake | 1009.glb | Complete binding | No valid animations |
| #1021 | Raging Bolt | 1021.glb | Partial | No valid animations |

## Recommendation

Test the 17 structurally compatible candidates in the viewer without overwriting existing Switch-model GLBs, while obtaining proper licensing/redistribution authorization. Inspect the eight additional animated-but-idle-uncertain candidates for genuine idle action names. Do not classify texture-incomplete or static/T-pose candidates as finished.

The CI run's artifact contains `report.json`, `report.tsv`, and `summary.md` with further GLB details such as Draco compression, animation clip names, and material counts. 
