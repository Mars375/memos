"""Tests for the AutoTagger — zero-LLM memory type classification."""

import pytest

from memos.tagger import TYPE_TAGS, AutoTagger

# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def tagger():
    return AutoTagger()


# ── Decision patterns ─────────────────────────────────────────────────

class TestDecision:
    def test_en_we_decided(self, tagger):
        assert "decision" in tagger.tag("We decided to use PostgreSQL for the project")

    def test_en_i_decided(self, tagger):
        assert "decision" in tagger.tag("I decided to refactor the module")

    def test_en_going_with(self, tagger):
        assert "decision" in tagger.tag("We're going with Redis for caching")

    def test_en_the_choice_is(self, tagger):
        assert "decision" in tagger.tag("The choice is between A and B")

    def test_en_agreed_to(self, tagger):
        assert "decision" in tagger.tag("We agreed to postpone the release")

    def test_en_ruled_out(self, tagger):
        assert "decision" in tagger.tag("We ruled out the monolith approach")

    def test_en_settled_on(self, tagger):
        assert "decision" in tagger.tag("We settled on Vue.js for the frontend")

    def test_fr_j_ai_decide(self, tagger):
        assert "decision" in tagger.tag("J'ai décidé de migrer vers ARM64")

    def test_fr_on_a_choisi(self, tagger):
        assert "decision" in tagger.tag("On a choisi Docker pour le déploiement")

    def test_fr_le_choix_est(self, tagger):
        assert "decision" in tagger.tag("Le choix est fait : on utilise Python")

    def test_fr_validee(self, tagger):
        assert "decision" in tagger.tag("La décision est validée par l'équipe")


# ── Preference patterns ───────────────────────────────────────────────

class TestPreference:
    def test_en_i_prefer(self, tagger):
        assert "preference" in tagger.tag("I prefer dark mode over light mode")

    def test_en_my_favorite(self, tagger):
        assert "preference" in tagger.tag("My favorite editor is Neovim")

    def test_en_i_like(self, tagger):
        assert "preference" in tagger.tag("I really like the new API design")

    def test_en_i_hate(self, tagger):
        assert "preference" in tagger.tag("I hate dealing with XML configs")

    def test_en_best_option(self, tagger):
        assert "preference" in tagger.tag("The best option is clearly Rust")

    def test_fr_j_aime(self, tagger):
        assert "preference" in tagger.tag("J'aime les interfaces minimalistes")

    def test_fr_je_prefere(self, tagger):
        assert "preference" in tagger.tag("Je préfère les réponses concises")


# ── Milestone patterns ────────────────────────────────────────────────

class TestMilestone:
    def test_en_deployed(self, tagger):
        assert "milestone" in tagger.tag("The new version is deployed to production")

    def test_en_shipped(self, tagger):
        assert "milestone" in tagger.tag("We shipped the feature yesterday")

    def test_en_completed(self, tagger):
        assert "milestone" in tagger.tag("The migration is completed successfully")

    def test_en_launched(self, tagger):
        assert "milestone" in tagger.tag("We launched the v2 API")

    def test_en_went_live(self, tagger):
        assert "milestone" in tagger.tag("The dashboard went live at midnight")

    def test_fr_terminee(self, tagger):
        assert "milestone" in tagger.tag("La migration est terminée")

    def test_fr_deploiee(self, tagger):
        assert "milestone" in tagger.tag("L'application est déployée sur le serveur")

    def test_fr_livree(self, tagger):
        assert "milestone" in tagger.tag("La feature est livrée au client")


# ── Problem patterns ──────────────────────────────────────────────────

class TestProblem:
    def test_en_bug(self, tagger):
        assert "problem" in tagger.tag("There's a bug in the auth module")

    def test_en_broken(self, tagger):
        assert "problem" in tagger.tag("The build is broken after the merge")

    def test_en_crashed(self, tagger):
        assert "problem" in tagger.tag("The server crashed at 3am")

    def test_en_error(self, tagger):
        assert "problem" in tagger.tag("Getting an error when calling the API")

    def test_en_failed(self, tagger):
        assert "problem" in tagger.tag("The deployment failed due to timeout")

    def test_en_regression(self, tagger):
        assert "problem" in tagger.tag("This is a regression from last week")

    def test_fr_erreur(self, tagger):
        assert "problem" in tagger.tag("Il y a une erreur dans le module")

    def test_fr_probleme(self, tagger):
        assert "problem" in tagger.tag("Le problème vient du cache")


# ── Emotional patterns ────────────────────────────────────────────────

class TestEmotional:
    def test_en_frustrated(self, tagger):
        assert "emotional" in tagger.tag("I'm frustrated with the slow CI")

    def test_en_excited(self, tagger):
        assert "emotional" in tagger.tag("I'm excited about the new release")

    def test_en_proud(self, tagger):
        assert "emotional" in tagger.tag("I'm proud of what we built")

    def test_en_stressed(self, tagger):
        assert "emotional" in tagger.tag("Feeling stressed about the deadline")

    def test_fr_frustrant(self, tagger):
        assert "emotional" in tagger.tag("C'est frustrant ces timeouts")

    def test_fr_content(self, tagger):
        assert "emotional" in tagger.tag("Je suis content du résultat")


# ── Fact patterns ─────────────────────────────────────────────────────

class TestFact:
    def test_en_there_are_number(self, tagger):
        assert "fact" in tagger.tag("There are 42 instances running")

    def test_en_according_to(self, tagger):
        assert "fact" in tagger.tag("According to the docs, it should work")

    def test_fr_il_y_a(self, tagger):
        assert "fact" in tagger.tag("Il y a 3 serveurs en production")


# ── Action patterns ───────────────────────────────────────────────────

class TestAction:
    def test_en_need_to(self, tagger):
        assert "action" in tagger.tag("We need to update the dependencies")

    def test_en_todo(self, tagger):
        assert "action" in tagger.tag("TODO: fix the tests before merging")

    def test_en_let_s(self, tagger):
        assert "action" in tagger.tag("Let's refactor the API layer")

    def test_fr_il_faut(self, tagger):
        assert "action" in tagger.tag("Il faut mettre à jour les dépendances")

    def test_fr_on_doit(self, tagger):
        assert "action" in tagger.tag("On doit corriger ce bug avant la release")


# ── Question patterns ─────────────────────────────────────────────────

class TestQuestion:
    def test_question_mark(self, tagger):
        assert "question" in tagger.tag("What time is the meeting?")

    def test_how_to(self, tagger):
        assert "question" in tagger.tag("How to configure the proxy?")

    def test_why(self, tagger):
        assert "question" in tagger.tag("Why is the service down?")

    def test_pourquoi(self, tagger):
        assert "question" in tagger.tag("Pourquoi le build échoue")


# ── Multi-tag classification ──────────────────────────────────────────

class TestMultiTag:
    def test_problem_emotional(self, tagger):
        """The build is broken AND I'm frustrated should give both tags."""
        tags = tagger.tag("The build is broken and I'm frustrated with the CI")
        assert "problem" in tags
        assert "emotional" in tags

    def test_milestone_decision(self, tagger):
        tags = tagger.tag("We decided to deploy and the release is completed")
        assert "decision" in tags
        assert "milestone" in tags

    def test_action_question(self, tagger):
        tags = tagger.tag("We need to fix the issue. Why is it happening?")
        assert "action" in tags
        assert "question" in tags


# ── Edge cases ────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_string(self, tagger):
        assert tagger.tag("") == []

    def test_whitespace_only(self, tagger):
        assert tagger.tag("   ") == []

    def test_no_match(self, tagger):
        """Generic content should return no type tags."""
        tags = tagger.tag("The cat sat on the mat and looked at the wall")
        assert tags == []

    def test_case_insensitive(self, tagger):
        assert "decision" in tagger.tag("WE DECIDED TO USE DOCKER")

    def test_mixed_case(self, tagger):
        assert "milestone" in tagger.tag("The Feature Is DePLOYed")

    def test_partial_word_no_match(self, tagger):
        """'deploy' without the full pattern should not match 'deployed'."""
        # 'deployment' doesn't match any milestone pattern directly
        tags = tagger.tag("We need a deployment strategy")
        assert "milestone" not in tags


# ── has_type_tags / auto_tag ──────────────────────────────────────────

class TestAutoTag:
    def test_has_type_tags_positive(self, tagger):
        assert tagger.has_type_tags(["decision", "project-x"]) is True

    def test_has_type_tags_negative(self, tagger):
        assert tagger.has_type_tags(["project-x", "backend"]) is False

    def test_has_type_tags_empty(self, tagger):
        assert tagger.has_type_tags([]) is False

    def test_auto_tag_no_existing(self, tagger):
        tags = tagger.auto_tag("We decided to use Rust")
        assert "decision" in tags

    def test_auto_tag_with_existing_non_type(self, tagger):
        tags = tagger.auto_tag("We decided to use Rust", existing_tags=["backend"])
        assert "decision" in tags

    def test_auto_tag_respects_existing_type(self, tagger):
        """If existing tags already have a type tag, don't add more."""
        tags = tagger.auto_tag("We decided to deploy", existing_tags=["milestone"])
        assert tags == []

    def test_auto_tag_no_duplicate(self, tagger):
        tags = tagger.auto_tag("We decided to use Rust", existing_tags=["decision"])
        assert "decision" not in tags


# ── tag_detailed ──────────────────────────────────────────────────────

class TestTagDetailed:
    def test_detailed_returns_matches(self, tagger):
        result = tagger.tag_detailed("The build is broken and I'm frustrated")
        assert "problem" in result
        assert "emotional" in result
        assert len(result["problem"]) > 0

    def test_detailed_empty(self, tagger):
        result = tagger.tag_detailed("")
        assert result == {}


# ── Custom patterns ───────────────────────────────────────────────────

class TestCustomPatterns:
    def test_custom_tag(self):
        t = AutoTagger(custom_patterns={"custom": [r"\bSUPER_SPECIAL\b"]})
        assert "custom" in t.tag("This is a SUPER_SPECIAL case")

    def test_augment_existing_tag(self):
        t = AutoTagger(custom_patterns={"decision": [r"\bCHOICE_MADE\b"]})
        tags = t.tag("CHOICE_MADE for the backend stack")
        assert "decision" in tags


# ── TYPE_TAGS constant ────────────────────────────────────────────────

class TestTypeTagsConstant:
    def test_all_categories_present(self):
        expected = {"decision", "preference", "milestone", "problem",
                    "emotional", "fact", "action", "question"}
        assert TYPE_TAGS == expected


# ── Integration: learn() auto-tags ────────────────────────────────────

class TestLearnAutoTag:
    def test_learn_auto_tags_decision(self):
        """MemOS.learn() should auto-append type tags."""
        from memos import MemOS
        mem = MemOS(backend="memory")
        item = mem.learn("We decided to use Kubernetes for orchestration", tags=["infra"])
        assert "decision" in item.tags
        assert "infra" in item.tags

    def test_learn_preserves_existing_type_tag(self):
        """If user passes a type tag, auto-tagger should not add more."""
        from memos import MemOS
        mem = MemOS(backend="memory")
        item = mem.learn("The deployment is done", tags=["milestone", "release"])
        assert "milestone" in item.tags
        assert "release" in item.tags
        # milestone already present → auto-tagger should skip

    def test_learn_no_type_tag_for_generic(self):
        """Generic content should not get auto-tags."""
        from memos import MemOS
        mem = MemOS(backend="memory")
        item = mem.learn("The weather is nice today", tags=["daily"])
        assert item.tags == ["daily"]
