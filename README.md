# **Convoy**

Pack your entire Python project and all its dependencies into a single, executable .convoy file.

## **Install**

pip install \-e .
or use setup.py

## **Usage**

**1\. Create a convoy.toml in your project root:**

\[file\]  
main \= "main.py"

\[settings\]  
compression \= 6  
libs \= "pyside6, PIL, matplotlib"

Alternatively, run convoy-settings to generate this configuration file via a GUI.

**2\. Build:**

convoy build         \# Standard build with animated output  
convoy build \--fast  \# Silent build, just ships it

**3\. Run:**

convoy run myapp.convoy

**4\. Settings GUI:**

convoy-settings

## **Crucial Note on Dependencies & Sub-imports**

Convoy **does not trace transitive dependencies or sub-imports**. It only bundles exactly what you tell it to.

If you are using complex libraries that rely on sub-modules (such as pyside6, matplotlib, etc.), you must explicitly declare every single required package/sub-package in the libs setting of your convoy.toml. If a library is missing its dependencies at runtime, the bundled executable will fail to run.

## **How It Works**

1. **Project & Dependency Bundling:** Convoy automatically gathers **everything** located in the same directory as your convoy.toml file—including all files, folders, and nested subfolders—alongside the specific external libraries you requested from your active Python environment.  
2. **Compression:** The entire package is compressed into a single .convoy binary.  
3. **Execution:** When executed, the bundle extracts to an isolated, private temporary directory, runs, and is immediately wiped upon exit. Nothing permanently remains on the host disk.

## **The .convoy File Format**

\[8 bytes\]  Magic header (CONVOY\\x00\\x01)  
\[4 bytes\]  Compressed payload length  
\[N bytes\]  zlib-compressed bundle  
