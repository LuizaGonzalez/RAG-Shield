# Comparación de configuraciones

Modelo: groq / qwen/qwen3.8-27b

| Configuración | ASR | IC 95 % | Rango entre rondas | Recuperación doc. malicioso | Contaminadas | Falsos positivos | Utilidad preservada | Acción insegura | Sobre-bloqueo | Latencia media | Latencia adicional |
|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline | 47.37 % | 32.48–62.74 % | 42.86–60.0 % | 89.47 % | 18.42 % | 0.0 % | 96.3 % | 53.33 % | 0.0 % | 8.2094 s | 0.0 s |
| capas_1_2 | 0.0 % | 0.0–7.87 % | 0.0–0.0 % | 88.89 % | 0.0 % | 0.0 % | 100.0 % | 0.0 % | 0.0 % | 10.0387 s | 1.8293 s |
| capa_3 | 22.22 % | 12.54–36.27 % | 22.22–22.22 % | 88.89 % | 22.22 % | 0.0 % | 88.57 % | 0.0 % | 0.0 % | 6.5414 s | -1.668 s |
| completo | 0.0 % | 0.0–16.82 % | 0.0–0.0 % | 89.47 % | 0.0 % | 0.0 % | 100.0 % | 0.0 % | 0.0 % | 25.6143 s | 17.4049 s |
