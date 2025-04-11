# Contributing to Melody Generation Project

Thank you for considering contributing to the Melody Generation Project! This document provides guidelines and instructions for contributing.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
  - [Development Environment](#development-environment)
  - [Docker Setup](#docker-setup)
- [How to Contribute](#how-to-contribute)
  - [Reporting Bugs](#reporting-bugs)
  - [Suggesting Enhancements](#suggesting-enhancements)
  - [Pull Requests](#pull-requests)
- [Development Workflow](#development-workflow)
  - [Branching Strategy](#branching-strategy)
  - [Commit Messages](#commit-messages)
- [Style Guidelines](#style-guidelines)
  - [Python Code Style](#python-code-style)
  - [Documentation](#documentation)

## Code of Conduct

Please be respectful and inclusive in all interactions related to this project.

## Getting Started

### Development Environment

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/melody-generation-project.git
   cd melody-generation-project
   ```


2. Set up a virtual environment:

```shellscript
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```


3. Install dependencies:

```shellscript
pip install -r requirements.txt
```




### Docker Setup

This project uses Docker containers for melody generation and vocal mixing:

1. Install Docker and Docker Compose
2. Build the containers:

```shellscript
docker-compose build
```


3. Start the containers:

```shellscript
docker-compose up -d
```




## How to Contribute

### Reporting Bugs

If you find a bug, please create an issue with the following information:

- A clear, descriptive title
- Steps to reproduce the issue
- Expected behavior
- Actual behavior
- Screenshots or logs if applicable
- Environment details (OS, Python version, etc.)


### Suggesting Enhancements

For feature requests:

- Use a clear, descriptive title
- Provide a detailed description of the proposed feature
- Explain why this feature would be useful
- Consider including mockups or examples


### Pull Requests

1. Fork the repository
2. Create a new branch from `main`
3. Make your changes
4. Run tests and ensure they pass
5. Submit a pull request with a clear description of the changes


## Development Workflow

### Branching Strategy

- `main`: Production-ready code
- `develop`: Integration branch for features
- `feature/feature-name`: For new features
- `bugfix/bug-name`: For bug fixes


### Commit Messages

Follow the conventional commits format:

- `feat`: A new feature
- `fix`: A bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code changes that neither fix bugs nor add features
- `test`: Adding or modifying tests
- `chore`: Changes to the build process or auxiliary tools


Example: `feat: add job-specific directories for output files`

## Style Guidelines

### Python Code Style

- Follow PEP 8 guidelines
- Use 4 spaces for indentation
- Maximum line length of 88 characters
- Use docstrings for all functions, classes, and modules


### Documentation

- Keep documentation up-to-date with code changes
- Use clear, concise language
- Include examples where appropriate


## Project Structure

```plaintext
melody-generation-project/
├── app.py                 # Main Gradio web interface
├── job_manager.py         # Background job processing
├── models.py              # Database models
├── services.py            # Docker container interaction
├── docker-compose.yml     # Container configuration
├── requirements.txt       # Python dependencies
└── shared_data/           # Shared volume for files
    ├── input/             # Input audio files
    ├── melody_results/    # Generated MIDI files
    └── vocal_results/     # Generated vocal and mixed files
```
