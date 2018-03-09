# AttoBot

<img src="https://github.com/attobot/attobot/blob/master/img/attobot.png" alt="attobot">

AttoBot is a package release bot for Julia. It creates pull requests to Julia METADATA when releases are tagged in GitHub, as an alternative to the [`PkgDev.jl`](https://github.com/JuliaLang/PkgDev.jl) functions `register`, `tag` and `publish`.

## Usage

To set up AttoBot on your repository, go to https://github.com/integration/attobot and click "Configure" to select the repositories you wish to add. It will only operate on packages with the standard ".jl" suffix (all other packages will be ignored).

If the package is not yet [registered in METADATA.jl](http://docs.julialang.org/en/stable/manual/packages/#tagging-and-publishing-your-package), it will be automatically added when you make your first release.

### Creating a release
Releases are created via [GitHub releases](https://help.github.com/articles/creating-releases/): this is some extra functionality built on top of git tags that trigger a webhook used by AttoBot.

 1. Click on the "releases" link in the repository banner.
  <br/><img src="https://github.com/attobot/attobot/blob/master/img/release-1.png" alt="release link" width="610">
 2. Click "Draft new release"
  <br/><img src="https://github.com/attobot/attobot/blob/master/img/release-2.png" alt="draft new release" width="488">
 3. Enter a tag label in the appropriate [semver form](http://semver.org/) (i.e. `vX.Y.Z` where X,Y,Z are numbers): GitHub will create the tag if it doesn't already exist. Include any other details and click "Publish release".
 
AttoBot will then open a pull request against METADATA and CC you in the process. In certain cases AttoBot may open an issue on the repository if the release is not correct (e.g. if the tag is not in the correct form). If the pull request does not appear within 30 seconds or so, please [open an issue](https://github.com/attobot/attobot/issues/new).

### Updating/deleting a release
If you need to make a change before the release *before* the METADATA pull request has been merged (e.g. if you need to fix your Compat settings), the easiest option is to delete the release (and corresponding tag), then create a new release with the same version number; AttoBot will then update the existing pull request and make a comment that it has been updated. To delete a release and its tag:

 1. Click on the "releases" link in the repository banner.
  <br/><img src="https://github.com/attobot/attobot/blob/master/img/release-1.png" alt="release link" width="610">
 2. Click on the title of the release in question
  <br/><img src="https://github.com/attobot/attobot/blob/master/img/release-delete-1.png" alt="release title" width="517">
 3. Click "Delete".
  <br/><img src="https://github.com/attobot/attobot/blob/master/img/release-delete-2.png" alt="release delete" width="408">
 4. The tag still exists; click on the tag title
  <br/><img src="https://github.com/attobot/attobot/blob/master/img/tag-delete-1.png" alt="tag title" width="489">
 5. Click "Delete"
  <br/><img src="https://github.com/attobot/attobot/blob/master/img/tag-delete-2.png" alt="release title" width="368">

 
## Privacy statement

AttoBot receives the content of certain GitHub hooks, namely the `integration_installation` event (which doesn't appear to be documented, but in any case is ignored by AttoBot), and the [`release`](https://developer.github.com/v3/activity/events/types/#releaseevent) event. These contain certain publicly available details about the repository and the user who initiated the event. AttoBot will also make several subsequent queries via the public GitHub api to the repository in question. The contents of these may be retained in server logs.

The user who triggers the release will be marked as the commit author, and if their email is publicly available via GitHub, or they have made a commit to the repository in question using a public email address, then it will appear in the METADATA commit log. If you don't wish for this to happen, then you should [make your email address private](https://help.github.com/articles/keeping-your-email-address-private/).

AttoBot should not be enabled on private repositories: not only are these not supported by METADATA (thus any such pull requests will be rejected), but you may inadvertently leak private information.

## Credits

- <a href="http://www.freepik.com/free-photo/robot-with-clipboard-and-boxes_958200.htm">Image by kjpargeter / Freepik</a>
