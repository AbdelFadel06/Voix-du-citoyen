from dataclasses import dataclass

from ..base import EnvoiPushEchoue, FournisseurPush, JetonPushInvalide


@dataclass
class PushEnvoye:
    jeton: str
    titre: str
    message: str
    donnees: dict


class MemoirePush(FournisseurPush):
    """
    Tests uniquement : garde les notifications dans `MemoirePush.boite`.
    `jetons_invalides` et `simuler_echec` permettent de tester les erreurs du fournisseur.
    """

    boite: list[PushEnvoye] = []
    jetons_invalides: set[str] = set()
    simuler_echec = False

    @classmethod
    def vider(cls):
        cls.boite.clear()
        cls.jetons_invalides.clear()
        cls.simuler_echec = False

    def envoyer(self, jeton, titre, message, donnees):
        if jeton in self.jetons_invalides:
            raise JetonPushInvalide("Jeton inconnu du fournisseur.")
        if self.simuler_echec:
            raise EnvoiPushEchoue("Échec simulé du fournisseur push.")
        self.boite.append(PushEnvoye(jeton, titre, message, donnees))
