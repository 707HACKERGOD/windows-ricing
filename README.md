# ( ˶°ㅁ°) !! Windows Rice Orchestrator
A minimal, all-in-one Python script for theme, wallpaper, and music transitions with support for other apps.

![Screenshot](Screenshot%202026-10-04%20050828.png)
---
- Animated transitions between themes (wallpaper blend + music blend + custom color palettes swap)
- A vibe coded terminal script focused around doing a ricing showcase on Windows 11
- Works with YASB, Windows 11, possibly with older Windows too, the only experimental part of the script is calling a WorkerW window for reliable wallpaper transition animation. The limitation is that for some people desktop icons disappear for half a second during the wallpaper transition animation. I debugged it for about 12 hours and tried calling the real windows wallpaper transition animation but it's not as reliable. The script instead uses the same method as apps like Lively Wallpaper on microsoft store, plays a one time animation one layer above the actual wallpaper while updating the real wallpaper behind the stage.
---
🌟 Setup to recreate the screenshots 🌟 ₍^. .^₎⟆
1. Get Python 3, Ubuntu and fish terminal set up, I used the Linux packaged with windows 11 by default
3. Get YASB, Komorebi for YASB, Flow launcher. Optionally, I also used pipes.sh, winfetch, cmatrix, cava for windows. All of them can be customized further individually
4. For the weekday + clock on the wallpaper, use Rainmeter + Mond clock skin
5. For removing windows default task bar, right click it and change task bar settings. Also set wallpaper to "Picture" mode. Optionally use Windhawk to get a custom taskbar instead
6. Send the .py to any free AI in case there are any problems, there are all needed diagnostic tools included
7. WIP: you'll have to edit the paths to wallpaper and music folders, and per every theme you need wallpaper + YASB color theme + song
---
![Screenshot](Screenshot%202026-10-04%20051314.png)
![Screenshot](Screenshot%202026-10-04%20051346.png)
![Screenshot](Screenshot%202026-10-04%20125617.png)
![Screenshot](Screenshot%202026-10-04%20141235.png)
---
Deepseek V4 + GLM 5.3

🪼⋆｡𖦹°🫧⋆.ೃ࿔*:･
