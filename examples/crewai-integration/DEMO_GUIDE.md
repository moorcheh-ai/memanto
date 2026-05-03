# Creating a Visual Demo (Terminal Recording)

This guide explains how to create a terminal recording to demonstrate the CrewAI + Memanto integration.

## Option 1: Using Asciinema (Recommended)

Asciinema is a lightweight terminal recorder that creates shareable, playble recordings.

### Installation

```bash
# On macOS
brew install asciinema

# On Linux
sudo apt-get install asciinema  # Ubuntu/Debian
sudo yum install asciinema     # Fedora/CentOS

# Or with pip
pip install asciinema
```

### Recording the Demo

```bash
# Navigate to the example directory
cd examples/crewai-integration

# Start recording
asciinema rec memanto_crewai_demo.cast

# Run the quickstart demo (it's faster and clearer)
export MOORCHEH_API_KEY='your-api-key-here'
python quickstart.py

# Press Ctrl+D to stop recording when finished
```

### Playing Your Recording

```bash
# Play locally
asciinema play memanto_crewai_demo.cast

# Upload to asciinema.org (creates shareable link)
asciinema upload memanto_crewai_demo.cast
```

### Tips for Good Recordings

1. **Terminal Size**: Use a terminal window that's at least 80x24 characters
2. **Font Size**: Use a readable font size (14-16pt recommended)
3. **Timing**: Pause after key outputs to let viewers read
4. **Clean Environment**: Close unnecessary apps before recording

## Option 2: Using Loom

Loom provides screen recording with camera overlay.

### Installation

Download from [https://www.loom.com](https://www.loom.com)

### Recording Steps

1. Open Loom and start a new recording
2. Select your terminal window as the capture target
3. Optionally enable camera overlay for personal touch
4. Run the demo:
   ```bash
   export MOORCHEH_API_KEY='your-api-key-here'
   python quickstart.py
   ```
5. Stop recording when finished
6. Trim and edit if needed
7. Share the link

## Option 3: Using Recordit (Quick GIF)

[Recordit](https://recordit.co/) creates animated GIFs quickly.

### Steps

1. Go to [https://recordit.co/](https://recordit.co/)
2. Download and install the app
3. Select the terminal window
4. Record your terminal session
5. Upload and get a GIF link

## Scripting an Automated Demo

For a perfectly timed demo, create a script:

```bash
#!/bin/bash
# demo_script.sh

# Set API key
export MOORCHEH_API_KEY='your-api-key-here'

echo "Starting CrewAI + Memanto Demo..."
sleep 1

echo ""
echo "Running quickstart demo..."
sleep 1

python quickstart.py

echo ""
echo "Demo complete!"
sleep 2
```

Then record it:

```bash
chmod +x demo_script.sh
asciinema rec demo.cast ./demo_script.sh
```

## What to Show in Your Demo

A good demo should include:

1. **Setup** (10 seconds):
   - Show the terminal
   - Verify environment variables

2. **Quickstart Demo** (30-45 seconds):
   - Run `python quickstart.py`
   - Show memory storage
   - Show memory retrieval
   - Show RAG-based Q&A

3. **Full Demo** (optional, 1-2 minutes):
   - Run `python memanto_crewai_example.py`
   - Show multi-agent workflow
   - Show bonus contradiction handling

4. **Conclusion** (10 seconds):
   - Show success message
   - Mention next steps

## Example Demo Description

If you need to describe your demo in the PR, use this template:

```
## Demo Recording

I've created a terminal recording showing the CrewAI + Memanto integration:

**Link**: [Your asciinema or Loom link]

**What's shown**:
1. Quickstart demo (30s): Memory persistence across sessions
2. Full multi-agent demo (1m): Research Agent storing → Writer Agent retrieving
3. RAG-based Q&A: Answering questions using stored memories

**Key highlights**:
- ✅ Memories persist after session restart
- ✅ Cross-agent memory sharing works
- ✅ Semantic search retrieves relevant information
- ✅ RAG provides grounded answers
```

## Tips for a Professional Demo

- **Practice first**: Run the demo once before recording
- **Clear terminal**: Start with a clean terminal window
- **Good lighting**: If using camera overlay
- **Steady pace**: Don't rush through output
- **Highlight key moments**: Pause briefly after important results
- **Keep it short**: 30-60 seconds is ideal for quick demos

## Troubleshooting

### Recording shows wrong size

Resize your terminal before starting the recording:
```bash
# Set terminal to 80x24
resize -s 24 80  # Linux/Mac with resize
```

### Audio not working (Loom)

Check system permissions for microphone access in System Settings.

### Output is too fast

Add `sleep` commands in your script or pause manually during recording.

## Ready to Record?

1. Set your API key: `export MOORCHEH_API_KEY='your-key'`
2. Run `python quickstart.py` once to verify it works
3. Start your recording tool
4. Run the demo
5. Stop recording
6. Share the link!

Good luck! 🎬
