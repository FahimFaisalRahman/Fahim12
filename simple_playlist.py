import os
import requests
import getpass
import warnings
import datetime

# Suppress SSL warnings
warnings.filterwarnings('ignore', message='Unverified HTTPS request')

class JellyfinPlaylistGenerator:
    def __init__(self, server_url=None, api_key=None):
        self.server_url = server_url or os.environ.get('JELLYFIN_SERVER')
        self.api_key = api_key or os.environ.get('JELLYFIN_API_KEY')
        
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'X-Emby-Token': self.api_key if self.api_key else ''
        })
        
        # Handle self-signed certificates
        self.session.verify = False
        warnings.filterwarnings('ignore', message='Unverified HTTPS request')
        
        if not self.server_url or not self.api_key:
            self.prompt_for_credentials()
    
    def prompt_for_credentials(self):
        """Prompt user for credentials"""
        print("\n" + "="*50)
        print("Jellyfin Configuration")
        print("="*50)
        
        if not self.server_url:
            server_url = input("Enter Jellyfin Server URL: ").strip()
            if not server_url.startswith(('http://', 'https://')):
                server_url = f"http://{server_url}"
            self.server_url = server_url
        
        if not self.api_key:
            self.api_key = getpass.getpass("Enter Jellyfin API Key: ")
            self.session.headers.update({'X-Emby-Token': self.api_key})
    
    def get_libraries(self):
        """Get all media libraries from Jellyfin"""
        url = f"{self.server_url}/Library/MediaFolders"
        
        try:
            response = self.session.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                libraries = []
                
                for item in data.get('Items', []):
                    library_name = item.get('Name', '')
                    library_id = item.get('Id', '')
                    
                    # Filter for movie libraries
                    if library_name and ('movie' in library_name.lower() or 'movies' in library_name.lower()):
                        libraries.append({
                            'id': library_id,
                            'name': library_name,
                            'type': 'Movie'
                        })
                    # Also include generic libraries that might contain movies
                    elif library_name:
                        # Check what types this library contains
                        library_types = self.get_library_types(library_id)
                        if 'Movie' in library_types:
                            libraries.append({
                                'id': library_id,
                                'name': library_name,
                                'type': 'Mixed'
                            })
                
                return libraries
        except Exception as e:
            print(f"Error fetching libraries: {e}")
        
        return []
    
    def get_library_types(self, library_id):
        """Get content types available in a library"""
        url = f"{self.server_url}/Items"
        params = {
            'ParentId': library_id,
            'Recursive': 'false',
            'Limit': 1
        }
        
        try:
            response = self.session.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                items = data.get('Items', [])
                if items:
                    return [items[0].get('Type', 'Unknown')]
        except:
            pass
        
        return ['Unknown']
    
    def get_movies_from_library(self, library_name=None, library_id=None):
        """Fetch movies from a specific library"""
        url = f"{self.server_url}/Items"
        params = {
            'Recursive': 'true',
            'IncludeItemTypes': 'Movie',
            'Fields': 'MediaSources,Path,RunTimeTicks,Genres',
            'SortBy': 'SortName',
            'Limit': 1000
        }
        
        # Add library filter if specified
        if library_id:
            params['ParentId'] = library_id
        elif library_name:
            # We need to get library ID by name first
            libraries = self.get_libraries()
            for lib in libraries:
                if lib['name'].lower() == library_name.lower():
                    params['ParentId'] = lib['id']
                    break
        
        all_items = []
        start_index = 0
        
        print(f"Fetching movies from library: {library_name or 'All Libraries'}...")
        
        while True:
            params['StartIndex'] = start_index
            try:
                response = self.session.get(url, params=params, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    items = data.get('Items', [])
                    total = data.get('TotalRecordCount', 0)
                    
                    all_items.extend(items)
                    
                    if len(all_items) >= total:
                        break
                    
                    start_index += len(items)
                    print(f"  Fetched {len(all_items)}/{total} items...")
                else:
                    break
            except Exception as e:
                print(f"Error fetching items: {e}")
                break
        
        return all_items
    
    def get_all_movies(self, selected_libraries=None):
        """Get all movies from selected libraries"""
        all_movies = []
        
        if not selected_libraries or 'all' in selected_libraries:
            # Get movies from all libraries
            print("Fetching movies from all libraries...")
            movies = self.get_movies_from_library()
            all_movies.extend(movies)
        else:
            # Get movies from specific libraries
            for lib_name in selected_libraries:
                movies = self.get_movies_from_library(library_name=lib_name)
                if movies:
                    all_movies.extend(movies)
                    print(f"Found {len(movies)} movies in '{lib_name}'")
        
        return all_movies
    
    def get_stream_url_simple(self, item_id):
        """Get the simple streaming URL that works without headers"""
        # Using the format that worked for you
        return f"{self.server_url}/Videos/{item_id}/stream.mp4?static=true"
    
    def get_stream_url_with_key(self, item_id):
        """Get streaming URL with API key (if needed)"""
        return f"{self.server_url}/Videos/{item_id}/stream.mp4?api_key={self.api_key}&static=true"
    
    def generate_playlist_for_library(self, movies, library_name="All Movies", url_type="simple"):
        """Generate playlist for a specific library"""
        if not movies:
            return None
        
        # Create playlist content
        playlist = f"#EXTM3U\n"
        playlist += f"# Jellyfin Playlist - {library_name}\n"
        playlist += f"# Generated from: {self.server_url}\n"
        playlist += f"# Total movies: {len(movies)}\n"
        
        if url_type == "simple":
            playlist += f"# URL Format: {self.server_url}/Videos/ID/stream.mp4?static=true\n"
            playlist += f"# Note: May work without authentication in VLC\n"
        elif url_type == "with_key":
            playlist += f"# URL Format: {self.server_url}/Videos/ID/stream.mp4?api_key=XXX&static=true\n"
            playlist += f"# Note: Contains API key in URL\n"
        
        playlist += "\n"
        
        for movie in movies:
            item_id = movie.get('Id')
            name = movie.get('Name', 'Unknown')
            duration_ticks = movie.get('RunTimeTicks', 0)
            duration_sec = int(duration_ticks // 10000000) if duration_ticks else -1
            
            if item_id:
                # Get URL based on type
                if url_type == "simple":
                    url = self.get_stream_url_simple(item_id)
                elif url_type == "with_key":
                    url = self.get_stream_url_with_key(item_id)
                else:
                    url = self.get_stream_url_simple(item_id)
                
                playlist += f"#EXTINF:{duration_sec},{name}\n"
                playlist += f"{url}\n"
        
        return playlist
    
    def generate_playlists(self):
        """Generate playlists for all libraries"""
        print(f"\nConnecting to {self.server_url}...")
        
        # Test connection
        try:
            response = self.session.get(f"{self.server_url}/System/Info", timeout=10)
            if response.status_code == 200:
                server_name = response.json().get('ServerName', 'Jellyfin Server')
                print(f"✓ Connected to: {server_name}")
            else:
                print("✗ Connection failed")
                return False
        except Exception as e:
            print(f"✗ Cannot connect: {e}")
            return False
        
        # Get available libraries
        print("\nDiscovering media libraries...")
        libraries = self.get_libraries()
        
        if not libraries:
            print("No movie libraries found!")
            return False
        
        print(f"\nFound {len(libraries)} movie library(ies):")
        for i, lib in enumerate(libraries, 1):
            print(f"  {i}. {lib['name']} ({lib['type']})")
        
        # Let user select libraries
        print("\n" + "="*50)
        print("Library Selection")
        print("="*50)
        print("Select libraries to include:")
        print("1. All libraries (combined)")
        print("2. Individual libraries (choose specific ones)")
        
        choice = input("\nEnter choice (1 or 2): ").strip()
        
        selected_libraries = []
        library_movies = {}
        
        if choice == '1':
            print("\n✓ Will include ALL libraries")
            selected_libraries = ['all']
            
            # Get all movies
            all_movies = self.get_all_movies(selected_libraries)
            
            if all_movies:
                library_movies['All Movies'] = all_movies
                print(f"\nFound {len(all_movies)} total movies")
            
        elif choice == '2':
            print("\nSelect libraries (enter numbers separated by commas):")
            for i, lib in enumerate(libraries, 1):
                print(f"  {i}. {lib['name']}")
            
            selections = input("\nEnter library numbers (e.g., 1,2,3): ").strip()
            
            if selections:
                selected_nums = [s.strip() for s in selections.split(',')]
                
                for num in selected_nums:
                    if num.isdigit():
                        idx = int(num) - 1
                        if 0 <= idx < len(libraries):
                            lib_name = libraries[idx]['name']
                            selected_libraries.append(lib_name)
                            
                            # Get movies from this library
                            movies = self.get_movies_from_library(library_name=lib_name)
                            if movies:
                                library_movies[lib_name] = movies
                                print(f"✓ Added '{lib_name}' with {len(movies)} movies")
            
            if not library_movies:
                print("No libraries selected. Using all libraries.")
                selected_libraries = ['all']
                all_movies = self.get_all_movies(selected_libraries)
                if all_movies:
                    library_movies['All Movies'] = all_movies
        
        else:
            print("Invalid choice. Using all libraries.")
            selected_libraries = ['all']
            all_movies = self.get_all_movies(selected_libraries)
            if all_movies:
                library_movies['All Movies'] = all_movies
        
        if not library_movies:
            print("\n✗ No movies found in selected libraries!")
            return False
        
        # Ask for URL type
        print("\n" + "="*50)
        print("URL Type Selection")
        print("="*50)
        print("Choose URL type (based on what works in VLC):")
        print("1. Simple URLs (without API key) - RECOMMENDED")
        print("2. URLs with API key")
        print("3. Both types")
        
        url_choice = input("\nEnter choice (1-3): ").strip()
        
        url_types = []
        if url_choice == '1':
            url_types = ['simple']
            print("\n✓ Using simple URLs (without API key)")
        elif url_choice == '2':
            url_types = ['with_key']
            print("\n✓ Using URLs with API key")
            print("  Note: API key will be visible in URLs")
        elif url_choice == '3':
            url_types = ['simple', 'with_key']
            print("\n✓ Creating both URL types")
        else:
            url_types = ['simple']
            print("\n✓ Defaulting to simple URLs")
        
        # Generate playlists
        print("\n" + "="*50)
        print("Generating Playlists")
        print("="*50)
        
        saved_files = []
        
        # Generate playlists for each URL type
        for url_type in url_types:
            type_suffix = {
                'simple': '_simple',
                'with_key': '_with_api_key'
            }.get(url_type, '')
            
            print(f"\nGenerating {url_type} URL playlists...")
            
            # Generate individual library playlists
            for lib_name, movies in library_movies.items():
                if not movies:
                    continue
                
                # Create filename (safe for filesystem)
                safe_name = lib_name.replace(' ', '_').replace('/', '_').replace('\\', '_')
                filename = f"jellyfin_{safe_name}{type_suffix}.m3u"
                
                # Generate playlist
                playlist_content = self.generate_playlist_for_library(
                    movies, lib_name, url_type
                )
                
                if playlist_content:
                    try:
                        with open(filename, 'w', encoding='utf-8') as f:
                            f.write(playlist_content)
                        
                        saved_files.append(filename)
                        print(f"✓ Created: {filename} ({len(movies)} movies)")
                    except Exception as e:
                        print(f"✗ Error saving {filename}: {e}")
            
            # Generate combined playlist if multiple libraries
            if len(library_movies) > 1:
                all_movies_combined = []
                for movies in library_movies.values():
                    all_movies_combined.extend(movies)
                
                if all_movies_combined:
                    # Create combined playlist content
                    combined_playlist = f"#EXTM3U\n"
                    combined_playlist += f"# Jellyfin Playlist - All Movies\n"
                    combined_playlist += f"# Generated from: {self.server_url}\n"
                    combined_playlist += f"# Total movies: {len(all_movies_combined)}\n"
                    
                    if url_type == "simple":
                        combined_playlist += f"# URL Format: {self.server_url}/Videos/ID/stream.mp4?static=true\n\n"
                    elif url_type == "with_key":
                        combined_playlist += f"# URL Format: {self.server_url}/Videos/ID/stream.mp4?api_key=XXX&static=true\n\n"
                    
                    for movie in all_movies_combined:
                        item_id = movie.get('Id')
                        name = movie.get('Name', 'Unknown')
                        duration_ticks = movie.get('RunTimeTicks', 0)
                        duration_sec = int(duration_ticks // 10000000) if duration_ticks else -1
                        
                        if item_id:
                            if url_type == "simple":
                                url = self.get_stream_url_simple(item_id)
                            elif url_type == "with_key":
                                url = self.get_stream_url_with_key(item_id)
                            
                            combined_playlist += f"#EXTINF:{duration_sec},{name}\n"
                            combined_playlist += f"{url}\n"
                    
                    combined_filename = f"jellyfin_ALL_MOVIES{type_suffix}.m3u"
                    try:
                        with open(combined_filename, 'w', encoding='utf-8') as f:
                            f.write(combined_playlist)
                        
                        saved_files.append(combined_filename)
                        print(f"✓ Created: {combined_filename} ({len(all_movies_combined)} movies)")
                    except Exception as e:
                        print(f"✗ Error saving combined playlist: {e}")
        
        # Create summary file
        self.create_summary_file(saved_files, library_movies, url_types)
        
        print(f"\n{'='*60}")
        print("GENERATION COMPLETE!")
        print("="*60)
        print(f"\nCreated {len(saved_files)} playlist file(s):")
        for file in saved_files:
            print(f"  • {file}")
        
        total_movies = sum(len(movies) for movies in library_movies.values())
        print(f"\nTotal movies: {total_movies}")
        
        # Show usage instructions
        print("\n" + "="*60)
        print("USAGE INSTRUCTIONS:")
        print("="*60)
        
        if 'simple' in url_types:
            print("\n📺 SIMPLE URLs (jellyfin_*_simple.m3u):")
            print(f"  • URL Format: {self.server_url}/Videos/ID/stream.mp4?static=true")
            print("  • May work without authentication in VLC")
            print("  • Try this first - it worked for your test!")
        
        if 'with_key' in url_types:
            print("\n🔑 URLs WITH API KEY (jellyfin_*_with_api_key.m3u):")
            print(f"  • URL Format: {self.server_url}/Videos/ID/stream.mp4?api_key=XXX&static=true")
            print("  • Use if simple URLs don't work")
            print("  ⚠️  API key is visible in URLs")
        
        print("\n📋 HOW TO TEST:")
        print("1. Open VLC Media Player")
        print("2. Go to Media > Open Network Stream")
        print("3. Paste one of these URLs:")
        print("   - Simple: http://192.168.0.109:8096/Videos/ID/stream.mp4?static=true")
        print("   - With key: http://192.168.0.109:8096/Videos/ID/stream.mp4?api_key=XXX&static=true")
        print("4. If it plays, use that playlist type")
        
        print("\n🔧 TROUBLESHOOTING:")
        print("• If URLs don't play, check Jellyfin authentication settings")
        print("• Ensure 'Allow audio playback that requires no authentication' is enabled")
        print("• Check 'Allow video playback that requires no authentication' is enabled")
        print("• These settings are in Jellyfin Dashboard > Playback")
        
        print("="*60)
        
        return True
    
    def create_summary_file(self, saved_files, library_movies, url_types):
        """Create a summary README file"""
        current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        summary = f"""# Jellyfin Playlists Summary

## Generated from: {self.server_url}
## Date: {current_time}
## URL Types: {', '.join(url_types)}

## Playlists Created:
"""
        
        for file in saved_files:
            summary += f"- {file}\n"
        
        summary += "\n## Library Breakdown:\n"
        for lib_name, movies in library_movies.items():
            summary += f"- **{lib_name}**: {len(movies)} movies\n"
        
        total_movies = sum(len(movies) for movies in library_movies.values())
        summary += f"\n## Total Movies: {total_movies}"
        
        summary += f"""

## URL Formats Used:

### Simple URLs (jellyfin_*_simple.m3u):
{self.server_url}/Videos/ITEM_ID/stream.mp4?static=true

### URLs with API Key (jellyfin_*_with_api_key.m3u):
{self.server_url}/Videos/ITEM_ID/stream.mp4?api_key={self.api_key[:10]}...&static=true

## Why Simple URLs May Work:

1. **?static=true** parameter may bypass some authentication checks
2. Jellyfin may have "Allow playback without authentication" enabled
3. Your network may be trusted (local IP range)
4. Session cookies from browser may still be valid

## Testing:

To test which URL works:
1. Get a movie ID from Jellyfin web interface
2. Try in VLC: {self.server_url}/Videos/MOVIE_ID/stream.mp4?static=true
3. If it plays, use the "simple" playlists
4. If not, try with API key

## VLC Settings (if needed):

If authentication is required:
1. Open VLC > Tools > Preferences > Show All Settings
2. Input/Codecs > Access modules > HTTP
3. Add header: X-Emby-Token: {self.api_key}
4. OR use URLs with API key

## Security Note:

- URLs with API key expose your API key
- Anyone with the playlist can access your Jellyfin server
- Use simple URLs if they work
- Regenerate API key if playlist is shared accidentally
"""
        
        try:
            with open("PLAYLISTS_SUMMARY.txt", 'w', encoding='utf-8') as f:
                f.write(summary)
            print(f"\n✓ Summary saved to: PLAYLISTS_SUMMARY.txt")
        except:
            pass

def main():
    print("="*60)
    print("JELLYFIN SIMPLE PLAYLIST GENERATOR")
    print("="*60)
    print("\nThis script creates playlists using the URL format that")
    print("worked for you: http://server:port/Videos/ID/stream.mp4?static=true")
    print("\nNo VLC header configuration needed if this format works!")
    
    generator = JellyfinPlaylistGenerator()
    generator.generate_playlists()

if __name__ == "__main__":
    main()