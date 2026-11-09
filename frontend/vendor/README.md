| Browser distribution | Version | Source |
| --- | --- | --- |
| LiquidGlassJS | 0.12.0 | [Surdeddd/liquidglassjs](https://github.com/Surdeddd/liquidglassjs) |
| MiniSearch | 7.2.0 | [lucaong/minisearch](https://github.com/lucaong/minisearch) |
| Cyrillic to Translit JS | 3.2.1 | [greybax/cyrillic-to-translit-js](https://github.com/greybax/cyrillic-to-translit-js) |

These are the npm browser distributions. Their license files and third-party notices are kept beside them. KipClub serves the modules and worker from its own origin and includes them in offline builds.

The LiquidGlassJS lens worker is extracted verbatim into `lens-worker.js`. The library loads it by URL to comply with `worker-src 'self'`. MiniSearch's source map reference is omitted because source maps are excluded from deployment.
