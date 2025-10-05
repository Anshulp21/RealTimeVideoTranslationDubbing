import logging
from typing import Optional

try:
    from argostranslate import package as argos_package
    from argostranslate import translate as argos_translate
    ARGOS_AVAILABLE = True
except Exception:
    ARGOS_AVAILABLE = False

class ArgosTranslate:
    """
    Offline translation using Argos Translate models.
    Automatically installs the required model for (source -> target) if available.
    """
    def __init__(self):
        self.logger = logging.getLogger("rt_dub")
        if not ARGOS_AVAILABLE:
            self.logger.warning("argos not available; package not installed")

    def ensure_model(self, source: str, target: str) -> bool:
        if not ARGOS_AVAILABLE:
            return False
        try:
            # Check if languages are already installed
            installed_languages = argos_translate.get_installed_languages()
            for lang in installed_languages:
                if lang.code == (source or "en"):
                    for to_lang in lang.translations:
                        try:
                            if to_lang.to_language.code == target:
                                return True
                        except Exception:
                            pass
            # Try to find and install package
            self.logger.info("argos.update_index")
            try:
                argos_package.update_package_index()
            except Exception as e:
                self.logger.warning("argos.update_index.failed err=%s", e)
            available_packages = []
            try:
                available_packages = argos_package.get_available_packages()
            except Exception as e:
                self.logger.warning("argos.get_available_packages.failed err=%s", e)
                return False
            pkg = next((p for p in available_packages if getattr(p, 'from_code', None) == (source or 'en') and getattr(p, 'to_code', None) == target), None)
            if not pkg:
                self.logger.warning("argos.package_not_found pair=%s->%s", source, target)
                return False
            self.logger.info("argos.installing pair=%s->%s", source, target)
            try:
                path = pkg.download()
                argos_package.install_from_path(path)
                self.logger.info("argos.install.ok pair=%s->%s", source, target)
                return True
            except Exception as e:
                self.logger.warning("argos.install.failed err=%s", e)
                return False
        except Exception as e:
            self.logger.warning("argos.ensure_model.failed err=%s", e)
            return False

    def translate(self, text: str, source: str, target: str) -> str:
        if not text:
            return ""
        if not ARGOS_AVAILABLE:
            raise RuntimeError("ArgosTranslate not installed")
        ok = self.ensure_model(source, target)
        if not ok:
            # Still may translate if language exists already; try anyway
            self.logger.info("argos.ensure_model.not_ok proceeding to attempt translate")
        try:
            out = argos_translate.translate(text, (source or 'en'), target)
            return out or ""
        except Exception as e:
            self.logger.warning("argos.translate.failed err=%s", e)
            raise
