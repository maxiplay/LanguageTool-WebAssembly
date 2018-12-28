package com.writecontrol.ltwa;

import org.languagetool.JLanguageTool;
import org.languagetool.Language;
import org.languagetool.language.BritishEnglish;
import org.languagetool.rules.RuleMatch;

import java.io.IOException;
import java.util.List;

public class Client {
    public static void main(String[] args) throws IOException {

        Language english = new BritishEnglish();
        // List<Rule> rules = langTool.getAllRules();

         JLanguageTool langTool = new JLanguageTool(english);

       /* langTool.disableRule(HunspellRule.RULE_ID);
        langTool.disableRule(HunspellNoSuggestionRule.RULE_ID);*/

        List<RuleMatch> matchs = langTool.check("Les enfant aiment la soupe");

        System.out.println(matchs);

    }
}
