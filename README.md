# Retold recorded game processor/renamer

This is a pretty crude attempt to parse some metadata from Age of Mythology: Retold recorded games and offers a configurable way to rename them, in case you don't like the filenames produced by the game. Notably, it excludes the names of the participant players, which can make finding one game in particular quite hard!

It can also output the metadata table as JSON and the decompressed recorded game data, but that might not be useful to anyone ever.

# Usage

Grab the latest release from the releases section on the right.

Open `recprocessor.ini` in your favourite text editor (notepad should work fine) and add your recorded game folder as a `ReplayFolder` entry. The path in `ReplayFolder2` should be close to the correct one - but will need filling in with your username and steam ID. You can do other things here too if you really want to.

Run `recprocessor.exe` and it should try to do things. If it doesn't work, `_recprocessor.log` probably contains hints as to why.

You can also run this from source if the prebuilt binary doesn't work for any reason. Any reasonably recent Python 3 installation should be able to do this: it has no external dependencies.

## Notes

This does **not** work on non-multiplayer recorded games, because the game does not write the metadata table that this parses in single player games.
