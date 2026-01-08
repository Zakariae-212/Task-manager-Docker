# Atelier Full-Stack – Bachelor 3
Vue 3 + Symfony 6 ou Python (FlaskAPI) + MySQL + Docker

## 🎯 Objectif
Vous allez développer une application web moderne permettant de gérer des tâches :
- créer une tâche
- afficher la liste
- marquer comme terminée
- supprimer

Architecture :
Navigateur
   |
 Vue 3 (frontend)
   |
 API REST
   |
 Python (FlaskAPI)
   |
 MySQL (base de données)

## 🧰 Prérequis
Docker, Docker Compose, Git

Vérification :
```bash
docker --version
docker compose version
git --version
```

## 📥 Installation
Dézippez le projet puis :

puis dans la racine . :

```bash
docker compose up
```

Services :
| Service     | URL                                            |
| ----------- | ---------------------------------------------- |
| API Flask   | [http://localhost:8000](http://localhost:8000) |
| Front Vue   | [http://localhost:5173](http://localhost:5173) |
| MySQL       | localhost:3306                                 |


## 🧪 Tester l’API
http://localhost:8000
Doit afficher:

```json
{ "message": "API ready" }
```

## 🧩 Travail à réaliser
Vous allez compléter l’application pour qu’elle soit pleinement fonctionnelle.

### 1️⃣ Côté Back-end (Symfony ou Python FlaskAPI)

Vous devez créer :
| Élément | À faire                            |
| ------- | ---------------------------------- |
| Entité  | `Task`                             |
| Champs  | `id`, `title`, `done`, `createdAt` |
| Routes  | `GET`, `POST`, `PUT`, `DELETE`     |
| Base    | MySQL                              |


Exemple d’URL attendue :

GET http://localhost:8000/api/tasks


L’API devra permettre :
 - d’ajouter une tâche
 - de les lister
 - de les modifier
 - de les supprimer

### 2️⃣ Côté Front-end (Vue)

Vous devez créer les composants suivants :

| Composant  | Rôle                |
| ---------- | ------------------- |
| `TaskList` | Affiche les tâches  |
| `TaskForm` | Formulaire d’ajout  |
| `App.vue`  | Gère les appels API |


Le front doit appeler l’API avec fetch.

### 3️⃣ Fonctionnalités obligatoires

Votre application doit permettre :

 - Ajouter une tâche
 - Voir toutes les tâches
 - Supprimer une tâche
 - Marquer une tâche comme terminée

🧪 Exemple d’appel API

Créer une tâche depuis le front ou la console :
```js
fetch('http://localhost:8000/api/tasks', {
  method: 'POST',
  headers: {'Content-Type':'application/json'},
  body: JSON.stringify({ title: "Mon TP" })
})
```

## 📄 Rendu

À la fin du projet, vous devez rendre :
 - votre code (via Git)
 - un fichier README expliquant :
   - comment lancer le projet
   - ce que fait l’application
 - une démonstration fonctionnelle