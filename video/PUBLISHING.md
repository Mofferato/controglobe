# Publishing a Controglobe video

From a finished render to a published video and a post that brings people to the project.
`python build.py timeline` (and every `build.py motion`) writes the words for you into
`output/youtube/`: `title.txt`, `description.txt` (with the chapters of the current cut),
`tags.txt`, `pinned_comment.txt` and `checklist.txt`. Edit them as you like before pasting;
the links in them come from `publish:` in `config/project.yaml`.

## What to have ready

| File | What it is |
|---|---|
| `output/motion/controglobe_motion_<date-time>.mp4` | The video, with its soundtrack inside. Take the newest. |
| `output/thumbnail_1280x720.png` | The thumbnail (YouTube's size, under its 2 MB limit) |
| `output/captions.srt` | English subtitles, timed to the finished video |
| `output/youtube/*.txt` | Title, description, tags, pinned comment, checklist |

Watch the whole video once before uploading, on a phone as well as the PC: text that reads on
a monitor can be too small on a phone.

Custom thumbnails need a verified YouTube account: YouTube Studio > Settings > Channel >
Feature eligibility, then verify with a phone number. Do it a day early; it can take a while.

## Uploading, step by step

In YouTube Studio: **Create > Upload videos**, and choose the video file. Then:

**1. Details**

- **Title**: one line from `title.txt` (YouTube's limit is 100 characters). Keeping the format
  of the series people already search for helps them find it.
- **Description**: paste `description.txt`. The chapters are in it. YouTube turns the list into
  chapters only if the first is at 0:00, there are at least three, and each lasts at least ten
  seconds. The pipeline makes sure of all three, so do not edit the times by hand.
- **Thumbnail**: upload `output/thumbnail_1280x720.png`.
- **Playlists**: make one for the series (say "Controglobe: every year") and add the video.
- **Audience**: "No, it's not made for kids". A video marked for kids loses comments, the
  notification bell and end screens.
- **Show more**:
  - Paid promotion: no.
  - Altered content: see the next section.
  - Tags: paste `tags.txt`. They matter far less than the title and thumbnail.
  - Language: English. Caption certification: none.
  - Licence: Standard YouTube Licence, or Creative Commons (CC BY) if you want other creators to
    be free to reuse it. The encyclopedia itself is CC BY-SA.
  - Category: Education (Entertainment works too).
  - Comments: on. Sort by top.

**2. Video elements**

- **Subtitles**: Add > Upload file > With timing > `output/captions.srt`. Viewers who watch
  without sound, and viewers who speak other languages (YouTube translates subtitles), can then
  follow the events.
- **End screen**: the last ten seconds are the end card, with space on both sides of the logo.
  Add an element: put a Video (choose "Best for viewer" once you have several) or a Playlist on
  the left of the logo, and Subscribe on the right. Stretch both to the whole last ten seconds.
- **Cards**: small "i" pop-ups during the video. Add one or two where a viewer might want more,
  for example a Playlist card at the start of "Revolution and expansion". Cards and end screens
  can only link outside YouTube (the encyclopedia, say) once the channel is in the YouTube
  Partner Programme; until then link to your own videos, playlists or channel.

**3. Checks**

YouTube checks for copyright. The music and every sound effect are made in code for this
video and the map data is public domain, so there is nothing to claim. Wait for the check to
finish before publishing.

**4. Visibility**

- **Public**: out now.
- **Schedule**: pick a time your audience is awake. Weekend afternoons and evenings in Europe
  and the Americas suit mapping channels.
- **Premiere**: a public countdown page and a live chat while the video plays for the first
  time. For a first video it is the best way to meet the people who come: be in the chat.

**5. Afterwards**

- Post `pinned_comment.txt` as a comment under the video, then open its menu and Pin it.
- Heart and answer the first comments: the first hour teaches YouTube who the video is for.
- Put the link in the encyclopedia: the README's Video section can carry it.

## "Altered or synthetic content"

YouTube asks creators to say when a video is realistic altered or synthetic content: a real
person made to say or do something they did not, real footage of a real event or place
altered, or a realistic-looking scene that never happened. A stylised, openly fictional
alternate-history map is generally not what the rule is aimed at, but the wording changes, so
read the question as Studio asks it and answer honestly. Either way the description says how
the video was made, and saying so plainly is what the mapping community respects.

## The community post

### Where

- **Your own channel**: the Community (Posts) tab, with a frame or the thumbnail as the image.
- **WTF CD Foxy's community**: posts on Foxy's YouTube channel are made by the channel itself;
  anyone else can only comment there, and comments with links are often held back. Look for the
  community spaces the channel links to (its About page, video descriptions, pinned comments),
  such as a Discord server. Read the rules before posting: most have a channel for sharing
  your own work, and many have rules about AI-made content. Post in the right channel once, do
  not tag the creator, and do not suggest the channel endorses your video.
- **Other mapping communities**: the same care, one post each, in the space meant for it.

### How to write it

- Short, personal, one image, one link.
- Say what the video is, what is new about it, and why you made it.
- Be open about the AI, and precise about what is yours: the history, the canon and every
  creative decision. People react to AI far better when told plainly than when they find out.
- Be careful with "first": you cannot know it is the first, and someone will argue. "As far as
  I know, one of the first" is honest and still says what you mean.
- Say the project's message in one sentence (below).
- End with an invitation or a question, and answer every reply.
- Credit the series that inspired it.

### The message of the project

In the project's own words: one change, applied consistently. From 500 BCE the Global North and
the Global South trade their histories, and the land stays exactly where it is. So the
difference between the powers of the world, who industrialises, who colonises, who is colonised
and who writes the textbooks, is history, not geography or people.

### A draft

> I've made my first alternate-history mapping video, in the "every year" style so many of us
> love: **Alternate History of Arabia (in place of the United States)**, 500 BCE to 2026.
>
> The premise: the land stays exactly where it is, only history moves. From 500 BCE the Global
> North and the Global South trade their histories, so Arabia gets the United States' story:
> princely colonies of a Hindustani empire, a revolution, a civil war, two world wars and a
> cold war. That is the heart of the project: who industrialises, who colonises, who is
> colonised and who writes the textbooks is history, not something written into the land.
>
> It's also made in a new way. It's AI-assisted: the history, the canon and every creative
> decision are mine, and I built the whole pipeline with an AI coding assistant, from the
> borders drawn year by year on real coastlines (QGIS and Python) to the animation, the infobox
> and even the music, finished in DaVinci Resolve. As far as I know it's one of the first mapping
> videos made this way, and all of it is open source, so anyone can see exactly how.
>
> One of the biggest reasons I'm doing this is to make friends. Controglobe is an open
> worldbuilding project with a whole encyclopedia behind the video, and I want the team to be
> friends first: people who like maps, history, writing, art, music or code, building a world
> together. It can get more professional as it grows, but I want it to stay a place people
> enjoy.
>
> If that sounds like you, reply or message me. And thanks to WTF CD Foxy, whose videos
> inspired the format.
>
> Video: (link) · Encyclopedia: https://mofferato.github.io/controglobe/

## A friends-first team

- Give people somewhere to talk. GitHub issues suit decisions about canon and code; a Discord
  server suits getting to know each other. When you have one, put its invite link in
  `publish: community:` in `config/project.yaml` and the video description will carry it.
- Welcome each newcomer yourself, and give them a small first task: a flag, an event with its
  date, a translation, a frame to check.
- Credit every contributor in the description of the video they helped with.
- Keep the rules short while the team is small; `CONTRIBUTING.md` already has the house style.
  Add structure (roles, reviews, a schedule) when the team asks for it, not before.
