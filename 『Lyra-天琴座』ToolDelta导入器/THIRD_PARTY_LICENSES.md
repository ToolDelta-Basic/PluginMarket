# Third-party attribution

## Java and Bedrock block mappings

The Java-to-Bedrock mapping is derived from `GeyserMC/mappings-generator` commit
`29ea7df5cee9de843fa8c0a1ccc1b82577b7b341` for Java 26.2 and Bedrock
1.26.30.5. Classic Java 1.12 numeric ID/data definitions are sourced from
`PrismarineJS/minecraft-data` commit
`e426427e0b3c0456654e646c2291d2fd9e91ee1c`. Both projects are MIT licensed.

- https://github.com/GeyserMC/mappings-generator
- https://github.com/PrismarineJS/minecraft-data

Copyright (c) 2019-2020 GeyserMC

## BDX format reference

The BDX operation layout was implemented with reference to the MIT-licensed
`TriM-Organization/BDXConverter` project. It is not required at runtime.

Copyright (c) 2023 Minecraft Muti-Media Organization
Copyright (c) 2023 All contributors of TriM-Organization/BDXConverter

https://github.com/TriM-Organization/BDXConverter

## MIT license text

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## MCWorld LevelDB dependency

Lyra installs `amulet-leveldb==1.0.7` through ToolDelta's pip support plugin and
uses only its Mojang LevelDB API. The package is not bundled; users and
distributors must comply with the license shipped with the installed package.

- https://github.com/Amulet-Team/Amulet-LevelDB
- https://pypi.org/project/amulet-leveldb/

PyMCTranslate and Amulet Core conversion data are not included.
