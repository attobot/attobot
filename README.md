# AttoBot

AttoBot is a package release bot for Julia. It will creates pull requests to Julia METADATA when releases are tagged in GitHub.

## Usage

To set up AttoBot on your repository, go to https://github.com/integration/attobot and click "Configure" to select the repositories you wish to add. These should be Julia repositories which are already [registered in METADATA.jl](http://docs.julialang.org/en/release-0.5/manual/packages/#tagging-and-publishing-your-package).

To use, simply [create a release](https://help.github.com/articles/creating-releases/) in the repository with a tag label in the appropriate [semver form](http://semver.org/) (i.e. `vX.Y.Z` where X,Y,Z are numbers). AttoBot will then open a pull request against METADATA and CC you in the process.

If the pull request does not appear within 30 seconds or so, please [open an issue](https://github.com/attobot/attobot/issues/new).

## Credits

- <a href="http://www.freepik.com/free-photo/robot-with-clipboard-and-boxes_958200.htm">Image by kjpargeter / Freepik</a>