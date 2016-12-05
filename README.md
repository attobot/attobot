# AttoBot

<img src="https://github.com/attobot/attobot/blob/master/img/attobot.png" alt="attobot">

AttoBot is a package release bot for Julia. It will creates pull requests to Julia METADATA when releases are tagged in GitHub, as an alternative to `PkgDev.tag`/`PkgDev.publish`.

## Usage

To set up AttoBot on your repository, go to https://github.com/integration/attobot and click "Configure" to select the repositories you wish to add. These should be Julia repositories which are already [registered in METADATA.jl](http://docs.julialang.org/en/release-0.5/manual/packages/#tagging-and-publishing-your-package).

Releases are created via [GitHub releases](https://help.github.com/articles/creating-releases/): this is some extra functionality built on top of git tags that trigger a webhook used by AttoBot.

 1. Click on the "releases" link in the repository banner.
  <br/><img src="https://github.com/attobot/attobot/blob/master/img/release-1.png" alt="release link" width="610">
 2. Click "Draft new release"
  <br/><img src="https://github.com/attobot/attobot/blob/master/img/release-2.png" alt="draft new release" width="488">
 3. Enter a tag label in the appropriate [semver form](http://semver.org/) (i.e. `vX.Y.Z` where X,Y,Z are numbers): GitHub will create the tag if it doesn't already exist. Include any other details and click "Publish release".
 
AttoBot will then open a pull request against METADATA and CC you in the process. If the pull request does not appear within 30 seconds or so, please [open an issue](https://github.com/attobot/attobot/issues/new).

If you need to modify the release before the METADATA pull request has been merged, the easiest option is to delete the release and create a new version:

 1. Click on the "releases" link in the repository banner.
 2. Click on the title of the release in question
  <br/><img src="https://github.com/attobot/attobot/blob/master/img/release-delete-1.png" alt="release title" width="517">
 3. Click "Delete".
  <br/><img src="https://github.com/attobot/attobot/blob/master/img/release-delete-2.png" alt="release delete" width="408">
 
## Credits

- <a href="http://www.freepik.com/free-photo/robot-with-clipboard-and-boxes_958200.htm">Image by kjpargeter / Freepik</a>
