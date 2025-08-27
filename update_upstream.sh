#!/bin/bash

# Script to update the upstream Hummingbot submodule to the latest version

set -e

echo "🔄 Updating Hummingbot upstream..."

cd hummingbot-upstream

# Fetch latest changes
echo "📡 Fetching latest changes from upstream..."
git fetch origin

# Get the latest release tag
LATEST_TAG=$(git describe --tags --abbrev=0 origin/master 2>/dev/null || echo "")

if [ -n "$LATEST_TAG" ]; then
    CURRENT_TAG=$(git describe --tags --exact-match HEAD 2>/dev/null || echo "development")
    
    if [ "$CURRENT_TAG" != "$LATEST_TAG" ]; then
        echo "🏷️  Updating from $CURRENT_TAG to $LATEST_TAG"
        git checkout $LATEST_TAG
        
        cd ..
        
        # Update the submodule reference in the parent repo
        git add hummingbot-upstream
        
        echo "✅ Updated to Hummingbot $LATEST_TAG"
        echo "📝 Don't forget to commit the submodule update:"
        echo "    git commit -m 'Update Hummingbot to $LATEST_TAG'"
    else
        echo "✅ Already on latest version: $LATEST_TAG"
    fi
else
    echo "⚠️  No release tags found, staying on current commit"
fi

cd ..

echo "🔧 Reinstalling Hummingbot..."
cd hummingbot-upstream
pip install -e . --force-reinstall
cd ..

echo "✅ Update complete!"