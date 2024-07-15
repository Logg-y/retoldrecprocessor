# Retold recorded game processor/renamer

This is a pretty crude attempt to parse some metadata from Age of Mythology: Retold and offer a simple way to rename them, in case you don't like the filenames produced by the game (that notably excludes the names of the participant players).

It can also output the metadata table as JSON and the decompressed recorded game data, but that might not be useful to anyone ever.

This is based on recorded games produced by the beta build that was run on the 12-15th July 2024 and **might not hold for the game's actual release**. Multiple things in the parsing are pretty crude and I have had to deal with not really having any way to even guess the specifics of a few things - which means this has a good chance of needing more help later.

# Usage

At the moment there I can't see any point in building binaries for this, but Python 3 should run the .py file without any external dependencies. The .ini file will probably need updating to change the locations it looks for recorded games, and also configure the format of the renaming if you don't like my defaults.

This does not work on non-multiplayer recorded games, because the game does not write the metadata table that this parses to these recorded games.
