# Contributing to NPA Monitor Bot

Thank you for your interest in contributing to the NPA Monitor Bot! This document provides guidelines for contributing to the project.

## Code of Conduct

By participating in this project, you agree to maintain a respectful and inclusive environment for all contributors.

## How to Contribute

### Reporting Issues

1. **Search existing issues** first to avoid duplicates
2. **Use the issue template** when creating new issues
3. **Provide detailed information** including:
   - Steps to reproduce
   - Expected behavior
   - Actual behavior
   - Environment details (Python version, OS, etc.)

### Submitting Changes

1. **Fork the repository**
2. **Create a feature branch** from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Make your changes** following the coding standards
4. **Test your changes** thoroughly
5. **Commit with clear messages**:
   ```bash
   git commit -m "Add: brief description of your change"
   ```
6. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```
7. **Create a Pull Request** with a clear description

### Coding Standards

- **Follow PEP 8** Python style guidelines
- **Add type hints** for function parameters and return values
- **Write docstrings** for classes and public methods
- **Keep functions focused** and under 50 lines when possible
- **Use meaningful variable names**
- **Add comments** for complex logic

### Testing

- **Test manually** with a Telegram bot in development
- **Verify all commands** work as expected
- **Test error scenarios** and edge cases
- **Check database operations** don't break existing data

### Documentation

- **Update README.md** if adding new features
- **Add docstrings** for new functions and classes
- **Update environment variable documentation** if needed
- **Include examples** for new functionality

## Development Setup

See [DEVELOPMENT.md](DEVELOPMENT.md) for detailed setup instructions.

## Pull Request Guidelines

### Before Submitting

- [ ] Code follows PEP 8 style guidelines
- [ ] All new code has appropriate docstrings
- [ ] Manual testing completed
- [ ] No sensitive information in commits
- [ ] Branch is up to date with main

### PR Description Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Documentation update
- [ ] Refactoring

## Testing
Describe how you tested these changes

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] Manual testing performed
```

## Areas for Contribution

### High Priority
- Bug fixes and stability improvements
- Performance optimizations
- Error handling enhancements
- Documentation improvements

### Medium Priority
- New bot commands
- Additional data visualizations
- Monitoring and alerting features
- API integrations

### Low Priority
- UI/UX improvements
- Code refactoring
- Additional deployment options

## Getting Help

- **Check existing documentation** first
- **Search closed issues** for similar problems
- **Create an issue** with the "question" label
- **Be specific** about what you need help with

## Recognition

Contributors will be recognized in:
- README.md contributors section
- Release notes for significant contributions
- Special thanks for major features or fixes

Thank you for contributing to make NPA Monitor Bot better!
