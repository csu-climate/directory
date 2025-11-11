#!/usr/bin/env python3
"""
Build script for the member Portal
Processes YAML member files and generates static site
"""

import os
import json
import yaml
import shutil
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape

import urllib.parse
from pathlib import PurePosixPath


# Shared instructor repository - same for all members
INSTRUCTOR_REPO = "csu-climate/members"  # Replace with your instructor repo

def load_yaml_file(filepath):
    """Load and parse a YAML file"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def get_member_id_from_filename(filename):
    """Extract member ID from YAML filename"""
    return Path(filename).stem

def process_member_data(member_data, member_id):
    """Process member data and add computed fields"""
    member_data['id'] = member_id
    
    # Add shared instructor repo
    member_data['instructor_repo'] = INSTRUCTOR_REPO
    
    # Automatically set instructor repo path to match member ID
    member_data['instructor_repo_path'] = member_id
    
    # Use fallback for instructor email if not specified
    if 'instructor_email' not in member_data:
        member_data['instructor_email'] = "N/A"
    
    # All members must now use the materials format with explicit URLs
    # Legacy formats (notebook/notebooks) are no longer supported
    if 'materials' not in member_data:
        if 'notebook' in member_data or 'notebooks' in member_data:
            print(f"Warning: member {member_id} uses legacy format. Please convert to materials format with explicit URLs.")
            return None
        else:
            print(f"Error: member {member_id} has no materials section.")
            return None

    # Generate chemcompute launch from public_repo_url

    if "ChemCompute" in member_data["platforms"]:
        stub = "https://chemcompute.org/jupyterhub_internal/hub/user-redirect/git-pull?repo="
        
        # Parse the GitHub repo URL
        repo_url = member_data['public_repo_url']
        parsed = urllib.parse.urlparse(repo_url)
        repo_path = PurePosixPath(parsed.path).stem

        repo_url_encoded = urllib.parse.quote(repo_url)
        urlpath = f"lab/tree/{repo_path}/"
        urlpath_encoded = urllib.parse.quote(urlpath)

        # Construct full launch URL
        member_data['chemcompute_launch'] = (
            f"{stub}{repo_url_encoded}"
            f"&branch=main"
            f"&urlpath={urlpath_encoded}"
        )  
    
    return member_data

def build_members_json(members_dir, output_dir):
    """Build the members.json file from all YAML files"""
    members = []
    
    # Process all YAML files in members directory
    for yaml_file in Path(members_dir).glob('*.yml'):
        print(f"Processing {yaml_file.name}...")
        
        member_data = load_yaml_file(yaml_file)
        member_id = get_member_id_from_filename(yaml_file.name)
        processed_member = process_member_data(member_data, member_id)
        
        if processed_member is not None:
            members.append(processed_member)
        else:
            print(f"Skipping {yaml_file.name} due to processing errors")
    
    # Sort members by title
    members.sort(key=lambda x: x['title'])
    
    # Write members.json
    output_file = Path(output_dir) / 'members.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(members, f, indent=2, ensure_ascii=False)
    
    print(f"Generated {output_file} with {len(members)} members")
    return members

def build_member_pages(members, templates_dir, output_dir):
    """Build individual member pages from template"""
    
    # Setup Jinja2 environment
    env = Environment(
        loader=FileSystemLoader(templates_dir),
        autoescape=select_autoescape(['html', 'xml'])
    )
    
    # Load member template
    template = env.get_template('member.html')
    
    for member in members:
        print(f"Building member page for {member['id']}...")
        
        # Create member directory
        member_dir = Path(output_dir) / 'members' / member['id']
        member_dir.mkdir(parents=True, exist_ok=True)
        
        # Prepare template context - just member data
        context = member
        
        # Render template
        html_content = template.render(context)
        
        # Write member page
        member_file = member_dir / 'index.html'
        with open(member_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"Generated {member_file}")

def copy_static_files(source_dir, output_dir):
    """Copy index.html and any static assets"""
    
    # Copy index.html directly
    index_source = Path(source_dir) / 'index.html'
    index_dest = Path(output_dir) / 'index.html'

    css_source = Path(source_dir) / 'theme.css'
    css_dest = Path(output_dir) / 'theme.css'

    logo_source = Path(source_dir) / 'act-cms-logo.svg'
    logo_dest = Path(output_dir) / 'act-cms-logo.svg'
    
    if index_source.exists():
        shutil.copy2(index_source, index_dest)
        print(f"Copied {index_source} to {index_dest}")
    else:
        print(f"Warning: {index_source} not found")

    if css_source.exists():
        shutil.copy2(css_source, css_dest)
        print(f"Copied {css_source} to {css_dest}") 
    else:
        print(f"Warning: {css_source} not found")

    if logo_source.exists():
        shutil.copy2(logo_source, logo_dest)
        print(f"Copied {logo_source} to {logo_dest}")
    else:
        print(f"Warning: {logo_source} not found")   
    
    # Copy static directory if it exists
    static_source = Path(source_dir) / 'static'
    static_dest = Path(output_dir) / 'static'
    
    if static_source.exists():
        if static_dest.exists():
            shutil.rmtree(static_dest)
        shutil.copytree(static_source, static_dest)
        print(f"Copied static files from {static_source} to {static_dest}")

def validate_member_data(member_data, filename):
    """Validate member data has required fields"""
    required_fields = [
        'title', 'description', 'programming_skill', 'primary_course',
        'authors', 'format', 'scientific_objectives', 
        'cyberinfrastructure_objectives', 'platforms', 'materials',
        'public_repo_url'
    ]
    
    # Optional instructor fields that should be validated if present
    optional_instructor_fields = {
        'student_level': str,
        'students_piloted': (int, float),
        'instructor_notes': str,
        'related_modules': list
    }
    
    missing_fields = []
    for field in required_fields:
        if field not in member_data:
            missing_fields.append(field)
    
    if missing_fields:
        print(f"Error: {filename} is missing required fields: {missing_fields}")
        return False
    
    # Validate optional instructor fields if present
    for field, expected_type in optional_instructor_fields.items():
        if field in member_data:
            value = member_data[field]
            if not isinstance(value, expected_type):
                print(f"Error: {filename} field '{field}' should be {expected_type.__name__ if hasattr(expected_type, '__name__') else expected_type}")
                return False
    
    # Validate related_modules if present
    if 'related_modules' in member_data:
        if not all(isinstance(module, str) for module in member_data['related_modules']):
            print(f"Error: {filename} related_modules should be a list of strings")
            return False
    
    # Check for legacy formats and reject them
    if 'notebook' in member_data or 'notebooks' in member_data:
        print(f"Error: {filename} uses legacy notebook/notebooks format. Please convert to materials format with explicit URLs.")
        return False
    
    # Validate materials structure
    if not isinstance(member_data['materials'], list):
        print(f"Error: {filename} materials field must be a list")
        return False
    
    if len(member_data['materials']) == 0:
        print(f"Error: {filename} materials list cannot be empty")
        return False
    
    for i, material in enumerate(member_data['materials']):
        required_material_fields = ['title', 'description', 'type', 'duration']
        for field in required_material_fields:
            if field not in material:
                print(f"Error: {filename} material {i+1} is missing required field: {field}")
                return False
        
        # Require at least one URL (github_url or colab_url)
        if 'github_url' not in material and 'colab_url' not in material:
            print(f"Error: {filename} material {i+1} must have either github_url or colab_url")
            return False
        
        # Validate URL format if present
        for url_field in ['github_url', 'colab_url']:
            if url_field in material:
                url = material[url_field]
                if not isinstance(url, str) or not url.startswith('http'):
                    print(f"Error: {filename} material {i+1} {url_field} must be a valid HTTP/HTTPS URL")
                    return False
    
    # Validate authors field
    if 'authors' in member_data:
        authors = member_data['authors']
        if not isinstance(authors, (list, str)):
            print(f"Error: {filename} authors field must be a list or string")
            return False
    
    return True

def main():
    """Main build process"""
    print("Building Member Directory ...")
    print("Note: Only materials format with explicit URLs is now supported.")
    
    # Define paths
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    members_dir = project_root / 'members'
    templates_dir = project_root / 'templates'
    output_dir = project_root / 'site'  # This will be pushed to gh-pages
    
    # Create output directory
    output_dir.mkdir(exist_ok=True)
    
    # Validate required directories exist
    if not members_dir.exists():
        print(f"Error: Member directory {members_dir} not found")
        return 1
    
    if not templates_dir.exists():
        print(f"Error: Templates directory {templates_dir} not found")
        return 1
    
    # Check for YAML files
    yaml_files = list(members_dir.glob('*.yml'))
    if not yaml_files:
        print(f"Error: No .yml files found in {members_dir}")
        return 1
    
    print(f"Found {len(yaml_files)} member files")
    
    # Validate all member files first
    valid_members = True
    for yaml_file in yaml_files:
        member_data = load_yaml_file(yaml_file)
        if not validate_member_data(member_data, yaml_file.name):
            valid_members = False
    
    if not valid_members:
        print("Error: Some member files have validation errors")
        print("Please fix the errors above and run the build again.")
        return 1
    
    try:
        # Build members.json
        members = build_members_json(members_dir, output_dir)
        
        if len(members) == 0:
            print("Error: No valid members found after processing")
            return 1
        
        # Build individual member pages
        build_member_pages(members, templates_dir, output_dir)
        
        # Copy static files
        copy_static_files(project_root, output_dir)
        
        print(f"\n✅ Build complete! Site generated in {output_dir}")
        print(f"📄 Generated {len(members)} member pages")
        print(f"🔗 Members available at: /members/[member-id]/")
        
        return 0
        
    except Exception as e:
        print(f"❌ Build failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    exit(main())
