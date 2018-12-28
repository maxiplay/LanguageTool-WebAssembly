package com.writeControl.teaVM;

import org.languagetool.JLanguageTool;
import org.languagetool.Language;
import org.languagetool.language.French;
import org.languagetool.rules.RuleMatch;
import org.languagetool.rules.spelling.hunspell.HunspellNoSuggestionRule;
import org.languagetool.rules.spelling.hunspell.HunspellRule;
import org.teavm.jso.dom.html.HTMLDocument;
import org.teavm.jso.dom.html.HTMLElement;

import java.io.IOException;
import java.util.List;

public class Client {
    public static void main(String[] args) throws IOException {

        Language french = new French();
        // List<Rule> rules = langTool.getAllRules();

         JLanguageTool langTool = new JLanguageTool(french);

       /* langTool.disableRule(HunspellRule.RULE_ID);
        langTool.disableRule(HunspellNoSuggestionRule.RULE_ID);*/

        List<RuleMatch> matchs = langTool.check("Les enfant aiment la soupe");

        HTMLDocument document = HTMLDocument.current();
        HTMLElement div = document.createElement("div");
        div.appendChild(document.createTextNode("Welcome to Language Tool"));
        document.getBody().appendChild(div);
    }
}
