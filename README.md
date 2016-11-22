# AttoBot

AttoBot is a package release bot for Julia.

## Usage

To set up AttoBot on your repository, go to https://github.com/integration/attobot and click "Configure" to select the repositories you wish to add. These should be Julia repositories which are already registered in [METADATA.jl](https://github.com/JuliaLang/METADATA.jl).

To use, simply [create a release](https://help.github.com/articles/creating-releases/) in the repository with a tag label of the appropriate semver form (i.e. `vX.Y.Z` where X,Y,Z are numbers). AttoBot will then open a pull request against METADATA and CC you in the process.

If the pull request does not appear within 30 seconds, please [open an issue](https://github.com/attobot/attobot/issues/new).