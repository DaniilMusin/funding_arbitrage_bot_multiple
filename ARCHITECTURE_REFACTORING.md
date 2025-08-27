# Architecture Refactoring: From Vendored to Modular

This document explains the architectural refactoring performed to decouple the funding arbitrage bot from the vendored Hummingbot code.

## Problem Statement

The original architecture had several issues:

1. **Vendored Dependencies**: The entire `hummingbot/` directory was copied into the repository
2. **Update Conflicts**: Updating Hummingbot required resolving merge conflicts in vendored files  
3. **Unclear Boundaries**: Custom code was mixed with upstream code in `core_ext/` and `controllers/`
4. **Maintenance Burden**: Any upstream changes could break local customizations

## Solution: Modular Architecture

### Key Changes Made

#### 1. Submodule Integration
- **Before**: `hummingbot/` directory with vendored code
- **After**: `hummingbot-upstream/` git submodule pointing to upstream repository
- **Benefit**: Clean updates without merge conflicts

#### 2. Custom Code Organization

```
strategies/                   # Custom trading strategies
├── funding_arbitrage/       # Main funding arbitrage strategy
│   ├── __init__.py         # Plugin interface
│   └── v2_funding_rate_arb.py

adapters/                    # Core functionality extensions
└── core_ext/               # Non-invasive core modifications
    ├── logging_conf.py     # Structured logging
    ├── state_sync.py       # Database synchronization  
    └── throttle.py         # Rate limiting

services/                    # Additional services
└── controllers/            # Custom trading controllers
    ├── directional_trading/
    ├── market_making/
    └── generic/
```

#### 3. Plugin System
- Strategies work as plugins to the core Hummingbot system
- Import system uses Python path manipulation for clean integration
- No modifications to upstream Hummingbot code required

#### 4. Installation & Update Scripts

- `install.sh`: Sets up submodule and dependencies
- `update_upstream.sh`: Updates Hummingbot to latest version
- Modified `start` script: Handles new directory structure

### Migration Steps Performed

1. **Backup & Remove Vendored Code**
   ```bash
   rm -rf hummingbot/
   ```

2. **Add Upstream Submodule**
   ```bash
   git submodule add https://github.com/hummingbot/hummingbot.git hummingbot-upstream
   ```

3. **Reorganize Custom Code**
   ```bash
   mv core_ext/* adapters/core_ext/
   mv controllers/* services/controllers/
   mv scripts/v2_funding_rate_arb.py strategies/funding_arbitrage/
   ```

4. **Update Configuration**
   - Modified `setup.py` to install only custom packages
   - Updated `start` script to use submodule
   - Created installation scripts

5. **Documentation Updates**
   - Updated README.md with new architecture
   - Added architecture deep dive section
   - Created installation instructions

## Benefits Achieved

### ✅ Easy Updates
```bash
# Before: Complex merge resolution
git pull upstream/master  # Conflicts likely

# After: Simple submodule update  
./update_upstream.sh      # No conflicts
```

### ✅ Clear Boundaries
- **Upstream code**: `hummingbot-upstream/` (never modified)
- **Custom strategies**: `strategies/` (isolated plugins)
- **Core extensions**: `adapters/` (clean interfaces)
- **Additional services**: `services/` (separate concerns)

### ✅ Version Control
- Submodule tracks specific Hummingbot versions
- Easy rollback if new version has issues
- Clear diff between local and upstream changes

### ✅ Development Workflow
```bash
# Install project
./install.sh

# Start trading
./start

# Update Hummingbot  
./update_upstream.sh
git commit -m "Update Hummingbot to vX.Y.Z"
```

## Technical Implementation Details

### Python Path Management
The startup scripts set up the Python path to include all necessary directories:
```bash
export PYTHONPATH=".:./hummingbot-upstream:./strategies:./adapters:./services:${PYTHONPATH}"
```

### Symbolic Linking
A symbolic link `hummingbot -> hummingbot-upstream/hummingbot` provides backward compatibility for imports.

### Plugin Registration
Custom strategies register themselves through standard Python package structure:

```python
# strategies/funding_arbitrage/__init__.py
from .v2_funding_rate_arb import FundingRateArbitrageConfig, FundingRateArbitrageV2
__all__ = ["FundingRateArbitrageConfig", "FundingRateArbitrageV2"]
```

### Adapter Pattern
Core extensions use the adapter pattern to modify behavior without patching upstream:

```python
# adapters/core_ext/logging_conf.py  
def setup():
    """Configure structlog for JSON output to stdout."""
    # Custom logging setup that doesn't modify Hummingbot core
```

## Future Maintenance

### Updating Hummingbot
1. Run `./update_upstream.sh`
2. Test functionality
3. Commit submodule update

### Adding New Strategies
1. Create new directory under `strategies/`
2. Implement strategy following plugin pattern
3. Export through `__init__.py`

### Core Extensions  
1. Add new adapters under `adapters/`
2. Use non-invasive patterns (dependency injection, configuration)
3. Avoid patching upstream files

### Version Pinning
The submodule allows pinning to specific Hummingbot versions for stability:

```bash
cd hummingbot-upstream
git checkout v1.15.0  # Pin to specific version
cd ..
git add hummingbot-upstream
git commit -m "Pin Hummingbot to v1.15.0"
```

## Conclusion

This refactoring achieves the goals outlined in the original issue:

1. **✅ Decoupled from vendored code**: Hummingbot is now a submodule
2. **✅ Easy updates**: No merge conflicts when updating upstream
3. **✅ Clear boundaries**: Custom code is isolated and organized
4. **✅ Transparent structure**: Each component has a clear purpose
5. **✅ Plugin architecture**: Strategies and extensions work as plugins

The new architecture makes the codebase much more maintainable while preserving all existing functionality.