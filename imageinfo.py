import io
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ExifTags
from typing import Optional

TAGS = ExifTags.TAGS
GPSTAGS = ExifTags.GPSTAGS

def get_exif_data(img: Image.Image) -> dict:
    """Extracts and formats human-readable EXIF metadata from an image."""
    exif_data = {}
    raw_exif = img.getexif()

    if not raw_exif:
        return exif_data

    for tag_id, value in raw_exif.items():
        tag_name = TAGS.get(tag_id, str(tag_id))
        
        # Handle GPS Info specifically
        if tag_name == "GPSInfo":
            gps_data = {}
            for gps_tag_id in value:
                gps_tag_name = GPSTAGS.get(gps_tag_id, str(gps_tag_id))
                gps_data[gps_tag_name] = value[gps_tag_id]
            exif_data["GPSInfo"] = gps_data
        else:
            # Clean up binary/byte data for safe text display
            if isinstance(value, bytes):
                try:
                    value = value.decode("utf-8", errors="ignore").strip()
                except Exception:
                    value = "<Binary Data>"
            exif_data[tag_name] = str(value)

    return exif_data

class ImageInfoCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="imageinfo", description="Analyze an uploaded image or image URL and extract full metadata.")
    @app_commands.describe(
        attachment="Upload the image file to analyze",
        url="Direct URL to an image (PNG, JPG, WEBP, GIF, etc.)"
    )
    async def image_info(
        self,
        interaction: discord.Interaction,
        attachment: Optional[discord.Attachment] = None,
        url: Optional[str] = None
    ):
        if not attachment and not url:
            await interaction.response.send_message(
                "❌ Please provide either an **uploaded image file** or an **image URL** to analyze.",
                ephemeral=True
            )
            return

        await interaction.response.defer()

        image_bytes: bytes = b""
        filename: str = "image"
        thumbnail_url: Optional[str] = None

        try:
            if attachment:
                if not attachment.content_type or not attachment.content_type.startswith("image/"):
                    await interaction.followup.send("❌ The uploaded file is not a valid image format.", ephemeral=True)
                    return
                image_bytes = await attachment.read()
                filename = attachment.filename
                thumbnail_url = attachment.url
            elif url:
                clean_url = url.strip()
                if not clean_url.startswith(("http://", "https://")):
                    await interaction.followup.send("❌ Please provide a valid HTTP/HTTPS image URL.", ephemeral=True)
                    return
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(clean_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                        if resp.status != 200:
                            await interaction.followup.send(f"❌ Failed to download image from URL (HTTP {resp.status}).", ephemeral=True)
                            return
                        content_type = resp.headers.get("Content-Type", "")
                        if content_type and not content_type.startswith("image/") and not clean_url.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")):
                            await interaction.followup.send("❌ The URL provided does not point to a valid image.", ephemeral=True)
                            return
                        image_bytes = await resp.read()
                
                filename = clean_url.split("?")[0].split("/")[-1] or "image.png"
                thumbnail_url = clean_url

            img = Image.open(io.BytesIO(image_bytes))

            # Basic Info
            width, height = img.size
            img_format = img.format or "Unknown"
            img_mode = img.mode
            file_size_kb = len(image_bytes) / 1024
            aspect_ratio = round(width / height, 2) if height > 0 else "N/A"

            # Build Discord Embed
            embed = discord.Embed(
                title=f"🔍  Image Analysis: {filename[:50]}",
                color=0x5865F2,
                timestamp=discord.utils.utcnow()
            )
            if thumbnail_url:
                embed.set_thumbnail(url=thumbnail_url)

            # General File Properties
            general_details = (
                f"**Resolution:** `{width} x {height} px`\n"
                f"**Aspect Ratio:** `{aspect_ratio}:1`\n"
                f"**Format:** `{img_format}`\n"
                f"**Color Mode:** `{img_mode}`\n"
                f"**File Size:** `{file_size_kb:.2f} KB`"
            )
            embed.add_field(name="📊  Basic Properties", value=general_details, inline=False)

            # Extract EXIF Data
            exif = get_exif_data(img)

            if exif:
                exif_lines = []
                priority_keys = ["Make", "Model", "DateTimeOriginal", "Software", "ExposureTime", "FNumber", "ISOSpeedRatings", "FocalLength"]
                
                for key in priority_keys:
                    if key in exif:
                        exif_lines.append(f"**{key}:** `{exif[key]}`")

                for key, val in exif.items():
                    if key not in priority_keys and key != "GPSInfo":
                        val_str = str(val)[:50] + ("..." if len(str(val)) > 50 else "")
                        exif_lines.append(f"**{key}:** `{val_str}`")

                if exif_lines:
                    embed.add_field(name="📷  Camera & EXIF Metadata", value="\n".join(exif_lines[:15]), inline=False)

                # GPS Coordinates
                gps_info = exif.get("GPSInfo")
                if isinstance(gps_info, dict) and "GPSLatitude" in gps_info and "GPSLongitude" in gps_info:
                    try:
                        lat = gps_info["GPSLatitude"]
                        lat_ref = gps_info.get("GPSLatitudeRef", "N")
                        lon = gps_info["GPSLongitude"]
                        lon_ref = gps_info.get("GPSLongitudeRef", "E")
                        
                        lat_str = f"{lat[0]}° {lat[1]}' {float(lat[2]):.1f}\" {lat_ref}"
                        lon_str = f"{lon[0]}° {lon[1]}' {float(lon[2]):.1f}\" {lon_ref}"
                        
                        embed.add_field(
                            name="📍  GPS Location Data",
                            value=f"**Latitude:** `{lat_str}`\n**Longitude:** `{lon_str}`",
                            inline=False
                        )
                    except Exception:
                        pass

            embed.set_footer(text="GKR Image Intelligence System")
            await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(f"❌ Failed to parse and analyze image: {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ImageInfoCog(bot))
    print("🔍 Image Info System Loaded")
