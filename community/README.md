# The Controglobe Discord

The project's home for talk: getting to know each other, arguing about canon, making maps and
art, and deciding what the next video is. GitHub stays the place where canon and code are
decided; the Discord is where people become friends first.

[`discord-server.json`](discord-server.json) is the whole server as data: roles, channels,
topics, permissions, the welcome and rules posts, the first forum posts and the onboarding
questions. [`build_server.py`](build_server.py) builds it on Discord from that file. Change the
file, run the script again, and the server follows.

## The name

**Controglobe**. It is short, it is the name of the channel, the site and the logo, and a
viewer who searches for it finds it. "Community project" is what the server *is*, so it goes in
the description, not the name. The tagline is the project's first rule:
*Geography is fixed. Only history moves.*

Other names that work, if you prefer one: **Controglobe HQ**, or **The Global Swap** (the
setting's own name). Change `server.name` in the JSON before building.

## The layout

```
ROLES   Founder · Moderator · Contributor                       listed apart
        Cartographer · Chronicler · Illuminator · Engineer      picked in onboarding,
        Translator · Producer · Historian · العربية             each with a colour
        Video Pings · Event Pings                                opt-in pings

📌 START HERE        👋・welcome  📜・rules  📢・announcements          read-only
💬 THE SQUARE        💬・general  🙋・introductions  🗣️・عربي  🎲・off-topic
🌍 THE GLOBAL SWAP   🧭・canon-talk  💡・proposals (forum)
🛠️ THE WORKSHOP      🌱・first-tasks (forum)  🗺️・maps  🎨・art-and-flags
                     ✍️・writing  💻・code  🔔・github-feed (read-only)
🎬 THE SERIES        🎥・videos  🔮・next-video  🖼️・showcase
🔊 VOICE             🔊 Lounge  🗺️ Map Room
🔒 STAFF             🛡️・mod-chat  📋・mod-log                        Moderators only
```

`python build_server.py --show` prints it from the JSON, and checks every name, topic and post
against Discord's limits.

Why it is shaped like this:

- **Small on purpose.** About twenty channels, not sixty: an empty server with many rooms feels
  deserted. `later` in the JSON lists what to add when the team asks for it (a real-history
  channel, a translation channel, a watch-party stage).
- **The categories follow the project.** *The Global Swap* is the canon, *The Workshop* is
  where things get made, *The Series* is the videos. The skill roles carry the setting's flavour
  (Cartographer, Chronicler, Illuminator) and pick themselves in onboarding.
- **Canon has a path.** Talk in `#canon-talk`; an idea that holds up becomes a post in the
  `#proposals` forum, tagged like the issue tracker (New canon, Contradiction, Question) plus
  Unassigned region and Fork; the ones that land go to a GitHub issue. The rules say plainly
  that chat is not canon, so nobody feels overruled by a conversation they missed.
- **Newcomers get a job.** `#first-tasks` is a forum of small jobs, seeded with four real ones:
  spot mistakes in the Arabia video, design the server's emoji, proofread an Arabic page, find the
  canon for an `inferred` data row. Anyone can add more.
- **The video feeds it.** `#next-video` opens with a poll on the eras, which answers the
  question the pinned comment asks. `#showcase` is where viewers post their own maps.
- **Arabic has a room.** The Arabia video and the Arabic edition will bring Arabic speakers;
  `#عربي` opens for anyone who picks العربية in onboarding.
- **Safe by default.** The rules add two that a server about colonial history needs: no hate
  against any people "in either timeline", and today's politics left at the door. AutoMod blocks
  slurs, sexual content, mention spam and suspected spam, and reports to `#mod-log`. New members
  need a verified email, and notifications default to mentions only.

## Building it on a PC (about ten minutes)

Claude has no Discord connector, so it cannot build the server from the Claude app. The script
does the same job from your PC, through a bot you make, use once and remove.

1. **Make the server.** In Discord: **+** (Add a Server) > **Create My Own** > *For a club or
   community*. Name it Controglobe. Discord's default `#general` is adopted; its other defaults
   are left alone for you to delete.
2. **Make the bot.** Go to <https://discord.com/developers/applications> > **New Application**,
   name it *Controglobe Builder*. Open **Bot** > **Reset Token** and copy the token. It is a
   password: never paste it in a chat, a Discord channel or GitHub.
3. **Invite the bot.** **OAuth2** > **URL Generator**: tick the scope `bot`, then the permission
   `Administrator`. Open the URL it makes, pick Controglobe, and authorise.
4. **Draw the icon** (optional): in `video/`, `python build.py logo` writes
   `output/logo_1024.png`, the Controglobe globe.
5. **Run the script** from this folder. It asks for the token and does not save it.

   ```
   python build_server.py --show
   python build_server.py --dry-run
   python build_server.py --icon ../video/output/logo_1024.png
   ```

   `--dry-run` reads the server and says what it would do without changing anything. The last
   line builds it: the roles in order, the categories and channels with their topics and
   permissions, Community switched on (announcements, forums, onboarding), the server settings,
   three AutoMod rules, the welcome and rules posts, the introductions prompt, the forum posts,
   the poll, and the Founder role for you. Running it again is safe: it finds what already exists
   by name and fixes it in place, and never deletes anything.
6. **Connect GitHub.** The script prints a webhook address for `#github-feed`. In the repository
   on GitHub: **Settings** > **Webhooks** > **Add webhook**, paste the address (it ends in
   `/github`), content type `application/json`, and choose Issues, Pull requests, Pushes and
   Releases.
7. **Remove the bot.** Kick *Controglobe Builder* from the member list, and in the Developer
   Portal press **Reset Token** once more so the old one stops working (or delete the
   application). Run steps 2 and 3 again if you ever want to rebuild.

If the script stops with *Missing Permissions*, open **Server Settings** > **Roles**, drag the
bot's role to the top, and run it again.

## Building it on a phone, by hand

Everything the script does can be done in the Discord app; it takes about 45 minutes. Work in
this order, copying names, topics and posts from `discord-server.json` (or from the guide page
Claude made for this).

1. **Create the server**: **+** > **Create My Own**, name Controglobe, upload the icon.
2. **Roles**: server name > **Settings** > **Roles** > **Create Role**, top to bottom as in
   the layout, with their colours. Tick *Display role members separately* for Founder,
   Moderator and Contributor. Give Moderator: Kick, Ban and Time out members, Manage Messages,
   Manage Threads, Manage Nicknames, View Audit Log, Mute, Deafen and Move Members, Manage Events.
3. **Categories and channels**: server name > **Create Category**, then **Create Channel**
   inside each. Make Staff a *Private Category* open to Moderator. Leave announcements and the
   two forums for step 5.
4. **Read-only channels** (welcome, rules, github-feed): channel > **Settings** >
   **Permissions** > @everyone: turn off *Send Messages*, *Send Messages in Threads*, *Create
   Public Threads* and *Create Private Threads*. Add Moderator and turn *Send Messages* on.
5. **Community**: **Settings** > **Enable Community**. Choose `#rules` as the rules channel and
   `#mod-log` for community updates. Then create `#announcements` (type Announcement, read-only
   like the others) and the forums `#proposals` and `#first-tasks` with their tags.
6. **Posts**: paste the welcome and rules posts, the introductions prompt, the forum posts, and
   make the poll in `#next-video` (the **+** by the message box > **Poll**).
7. **Safety**: **Settings** > **AutoMod**: turn on *Block mention spam*, *Block suspected spam
   content* and *Block commonly flagged words* (Sexual content, Slurs), with alerts to
   `#mod-log`. **Settings** > **Overview** > *Default Notification Settings*: *Only @mentions*.

## After building (by hand, either way)

**Onboarding** (Server Settings > Onboarding; needs Community). This is where people pick their
roles, so no reaction-role bot is needed.

- *Default channels*: welcome, rules, announcements, general, introductions, canon-talk,
  proposals, videos, next-video, showcase. The others open when someone picks what they like.
- *Questions*:

  | Question | Options → role, channels |
  |---|---|
  | What do you like to make? (several) | 🗺️ Maps → Cartographer, #maps · ✍️ Writing and canon → Chronicler, #writing · 🎨 Art → Illuminator, #art-and-flags · 💻 Code → Engineer, #code, #github-feed · 🌐 Translation → Translator, #writing, #عربي · 🎬 Video, music and sound → Producer · 📚 Real history → Historian · 👀 Just here to watch. Every making option also opens #first-tasks |
  | Which languages do you speak? (several) | 🔤 English · 🗣️ العربية → العربية, #عربي |
  | Want a ping? (several) | 🔔 New videos and premieres → Video Pings · 📅 Voice events and watch parties → Event Pings |

- *Server Guide*: the welcome line is the tagline; the to-dos are *Read the rules* (#rules),
  *Say hi* (#introductions), *Take a first task* (#first-tasks) and *Vote on the next video*
  (#next-video); the resource pages are #welcome and #rules.

**The invite link.** In `#welcome`: **Invite** > **Edit invite link** > *Expire after*: Never,
*Max number of uses*: No limit. A short custom address such as discord.gg/controglobe needs a
server at boost level 3, so use the generated one.

**Safety for moderators.** When you add moderators, **Settings** > **Safety Setup** >
*Require 2FA for moderator actions* (your own account needs 2FA first).

## Putting it on the channel

1. Put the invite in `video/config/project.yaml`, `publish: community:`, then run
   `python build.py timeline` in `video/`. `output/youtube/pinned_comment.txt` then leads with
   the Discord and ends by sending the "which era next?" question to the poll, and
   `description.txt` carries the link beside the encyclopedia's.
2. Under the video: post the pinned comment and pin it. If the video is already up, edit its
   description in YouTube Studio and add the same line: `Join the Discord: <invite>`.
3. On the channel: YouTube Studio > **Customisation** > **Profile** > **Links** > add
   *Discord* with the invite, so it shows on the channel page.
4. In `#announcements`, once the video is live:

   > **Alternate History of Arabia (in place of the United States): every year, 500 BCE to 2026**
   > is out. The United States' story, told on Arabia's land. Watch it, then tell us in
   > #videos what you spotted and vote in #next-video for the era that gets the next one.
   > (link)

End screens and cards can only link outside YouTube once the channel is in the YouTube Partner
Programme, so until then the pinned comment and the description are where the link lives.
Saying it out loud in the next video ("the Discord is in the pinned comment") works too.

## Changing it later

Edit `discord-server.json` and run `python build_server.py` again: names, topics, permissions
and order follow the file. It posts only into empty channels and new forums, so to change a post
that is already up, edit it in Discord. Save a snapshot any time with **Settings** >
**Server Template**; the template link rebuilds the same layout in a new server.
