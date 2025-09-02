#!/bin/bash

output_file="combined.txt"
> "$output_file"  # Clear the output file

# Find files with specific extensions or names
find . -type f \( \
  -name "Dockerfile" -o \
  -name "*.dockerfile" -o \
  -name "*.py" -o \
  -name "*.html" -o \
  -name "*.go" -o \
  -name "*.js" \
\) | while read -r file; do
  echo "===== $file =====" >> "$output_file"
  cat "$file" >> "$output_file"
  echo -e "\n\n" >> "$output_file"
done

echo "✅ Combined selected files into $output_file"
