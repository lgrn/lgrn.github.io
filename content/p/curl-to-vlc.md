---
title: "Using curl to pass videos to VLC on Apple TV"
date: 2023-09-13T19:08:00+02:00
draft: false
tags:
    - linux
---

VLC has always been a great piece of software, but one place where is
really shines is on iOS/tvOS since it allows you to play pretty much any
video file, and you can send that file over curl.

While this probably also works for iOS, this example will focus on the
use case of downloading a YouTube video, stripping it of sponsored
content and passing it on to VLC on an Apple TV. It's not that difficult, but you do
need [`yt-dlp`](https://github.com/yt-dlp/yt-dlp), `ffmpeg` and `curl`:

{{< code language="bash" title="tovlc.sh" id="1" expand="Show"
collapse="Hide" isCollapsed="false" >}}#!/bin/bash
/usr/bin/yt-dlp $1 -o output.mkv \
--sponsorblock-remove all \
--force-overwrites \
--merge-output-format mkv \
--embed-subs \
&& /usr/bin/curl -i \
-X POST 'http://appletv.local/upload.json' \
--form file='@output.mkv'
{{< /code >}}

This will:
* Run `yt-dlp` to download the video at the url passed as the argument
  to the script (`$1`)
    * Remove any sponsored content
    * Overwrite the output.mkv file if it already exists
    * Change the container to `mkv`
    * Embed any subtitles found
* Send a `POST` request to VLC using
  [`--form`](https://curl.se/docs/manpage.html#-F) to send the binary
  contents of the file as `file`.

  Having this script executable as `tovlc` in `/usr/bin` for example
  will allow you to then run things like:

  ```
  $ tovlc https://www.youtube.com/watch?v=foeov6Ahi4Y
  ```

  Note: I tried having `yt-dlp` passing the output to stdout with `-o -`
  followed by a pipe to curl with `--form file='@-'`, while this should
  work in theory I couldn't get it to work, so the above will require
  enough disk space to store the file before sending it to VLC.

  ## Additional reading

  * [yt-dlp usage and options](https://github.com/yt-dlp/yt-dlp#usage-and-options)