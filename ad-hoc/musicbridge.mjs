const SPOTIFY_CLIENT_ID = "9e64fe19b0794f66aea718e6c9692760";
const SPOTIFY_CLIENT_SECRET = "f6e67c13363d456ebd60b866e513f3ca";

const musicUrl = "https://open.spotify.com/track/3XHtGQBlfMHfKcXdTX7Mt0";
const isSpotify = musicUrl.includes("spotify.com");
const isApple = musicUrl.includes("apple.com");

// 1. Vytiahni metadata cez song.link
const songLinkRes = await fetch(`https://api.song.link/v1-alpha.1/links?url=${encodeURIComponent(musicUrl)}&userCountry=CZ`);
const songLinkData = await songLinkRes.json();
const entity = Object.values(songLinkData.entitiesByUniqueId || {})[0];

console.log("Skladba:", entity.title, "—", entity.artistName);

let convertedUrl = null;

if (isSpotify) {
  const query = encodeURIComponent(`${entity.title} ${entity.artistName}`);
  const itunesRes = await fetch(`https://itunes.apple.com/search?term=${query}&media=music&entity=song&limit=1&country=CZ`);
  const itunesData = await itunesRes.json();
  convertedUrl = itunesData.results?.[0]?.trackViewUrl;

} else if (isApple) {
  const tokenRes = await fetch("https://accounts.spotify.com/api/token", {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      "Authorization": "Basic " + Buffer.from(`${SPOTIFY_CLIENT_ID}:${SPOTIFY_CLIENT_SECRET}`).toString("base64"),
    },
    body: "grant_type=client_credentials",
  });
  const tokenData = await tokenRes.json();

  const query = encodeURIComponent(`track:${entity.title} artist:${entity.artistName}`);
  const spotifyRes = await fetch(`https://api.spotify.com/v1/search?q=${query}&type=track&limit=1&market=CZ`, {
    headers: { "Authorization": `Bearer ${tokenData.access_token}` },
  });
  const spotifyData = await spotifyRes.json();
  convertedUrl = spotifyData.tracks?.items?.[0]?.external_urls?.spotify;
}

console.log("Výsledok:", convertedUrl || "Nenašlo sa nič");
