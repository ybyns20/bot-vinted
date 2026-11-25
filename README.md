# Vinted Monitor — bot Discord à abonnements

## Fonctionnalités
- **Monitor Vinted** : 7 catégories et 31 sous-catégories (1 salon par sous-catégorie), modifiables dans `catalog.py`
- **3 offres** (Starter, Pro, Elite) : chacune débloque certaines catégories grâce à un rôle Discord
- **Keys liées au compte** : une key ne s'active qu'une fois, sur un seul compte Discord
- **Abonnements automatiques** : prolongation si même offre, upgrade avec conversion au pro-rata du temps restant, downgrade bloqué, rappel en MP 3 jours avant la fin, rôle retiré automatiquement à l'expiration, rôle remis si la personne revient sur le serveur
- **Factures** : formulaire (modal) avec nom, mail, adresse et entreprise → PDF numéroté (FAC-2026-00001) envoyé par mail. Le nom d'expéditeur se choisit avec `/admin mailname`
- **Panel** avec boutons : activer une key, mon abonnement, offres, ma facture, acheter

## Installation
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # puis remplis-le
.venv/bin/python bot.py
```
Dans le Discord Developer Portal, active l'intent **Server Members**. Invite le bot avec les permissions
`Manage Roles`, `Manage Channels`, `Send Messages`, `Embed Links`. **Le rôle du bot doit être au-dessus des rôles d'offres.**

## Démarrage
1. `/admin setup` : crée les rôles, les catégories et les salons avec les bonnes permissions
2. `/admin panel` dans ton salon #abonnement
3. `/admin genkey plan:Pro days:30 quantity:50` : télécharge le .txt et mets-le en stock sur **SellAuth / Sellix**, qui livre la key automatiquement après paiement (vente 100 % auto)

## Commandes
| Joueurs | Admin |
|---|---|
| `/redeem` `/abonnement` `/offres` | `/admin setup` `panel` `genkey` `revokekey` `give` `revoke` `info` `stats` `mailname` |

## À savoir
- **Mail** : Brevo (gratuit, 300 mails par jour) ou Gmail avec un mot de passe d'application. Mets une adresse de ton domaine dans `MAIL_FROM_ADDRESS` pour éviter les spams.
- **Factures légales** : il te faut un statut (micro-entreprise) et un SIRET dans `.env`.
- **Vinted** : le scraping est contraire à leurs CGU. Garde un `POLL_DELAY` raisonnable. Les IP de datacenter sont souvent bloquées : teste depuis ton PC ou un VPS résidentiel, et vérifie les `catalog_ids` dans `catalog.py`.
