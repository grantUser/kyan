# kyan - Bittorrent software for dogs

kyan is a public BitTorrent tracker project, originally forked from the [nyaa](https://github.com/nyaadevs/nyaa) project. This fork aims to bring the codebase up to date with current libraries and technologies, as the original project has not been updated for years.

## Project Name

The name "kyan" is inspired by the sound associated with small dogs, such as Chihuahuas. In contrast to "nyaa", which represents the sound of cats, "kyan" reflects the playful and energetic nature often associated with smaller canine companions.

## To-Do List

- Integrate Alembic for database migrations.
- Reintegrate tests for robust codebase validation.
- Add support for user pronouns.

## Changes from nyaa

Kyan includes several modifications and updates compared to the original nyaa project:

- **Updated Dependencies:** The codebase has been updated to use the latest versions of libraries and dependencies.
- **Refactored Codebase:** Significant refactoring has been done to improve code structure and maintainability.
- **Removals:** Elastic Search and full-text search have been removed to streamline the project.
- **Pronoun Support:** Added support for user pronouns to enhance user interactions.

## Configuration

1. **Update Configuration File:**
   - Open the configuration file located at `path/to/your/configuration/file`.
   - Update the necessary settings, such as API keys, database configurations, etc.

2. **Install Dependencies:**
   - Ensure you have [PDM](https://github.com/pdm-project/pdm) installed.
   - Run the following command to install project dependencies:
     ```
     pdm install
     ```

3. **Run Kyan:**
   - Execute the following command to run the Kyan project:
     ```
     pdm run kyan
     ```

   This will start the Kyan BitTorrent tracker.

## Prerequisites

- Python (version 3.10 or higher)
- [PDM](https://github.com/pdm-project/pdm)

## Installation

1. Clone the repository: `git clone https://github.com/votreutilisateur/kyan.git`
2. Change into the project directory: `cd kyan`
3. Install dependencies using PDM: `pdm install`

## Contributing

Contributions are welcome! If you would like to contribute to the project, please follow the guidelines in [CONTRIBUTING.md](CONTRIBUTING.md).

## License

This project is licensed under the [MIT License](LICENSE).

## Acknowledgments

- Original nyaa project: [nyaa](https://github.com/nyaadevs/nyaa)
- PDM: [PDM](https://github.com/pdm-project/pdm)

## Contact

For questions or concerns, please contact grantUser@skiff.com.
