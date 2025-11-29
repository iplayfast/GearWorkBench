jQuery(document).ready(function () {
  /**
   * Dismiss suggest addons
   */
  jQuery('#yaymail-suggest-addons-notice .yaymail-dismiss-suggest-addons-notice').on(
    'click',
    function () {
      jQuery('#yaymail-suggest-addons-notice .notice-dismiss').trigger('click');
    },
  );
  jQuery('#yaymail-suggest-addons-notice .yaymail-see-addons').on('click', function () {
    jQuery('#yaymail-suggest-addons-notice .notice-dismiss').trigger('click');
  });

  /**
   * Dismiss upgrade pro
   */
  jQuery('#yaymail-upgrade-notice .yaymail-dismiss-upgrade-notice').on('click', function () {
    jQuery('#yaymail-upgrade-notice .notice-dismiss').trigger('click');
  });
  jQuery('#yaymail-upgrade-notice .yaymail-upgrade-pro').on('click', function () {
    jQuery('#yaymail-upgrade-notice .notice-dismiss').trigger('click');
  });

  jQuery(document).on('click', '#yaymail-suggest-addons-notice .notice-dismiss', function () {
    handleDismiss();
  });

  jQuery(document).on('click', '#yaymail-upgrade-notice .notice-dismiss', function () {
    handleDismiss(true);
  });

  function handleDismiss(isUpgrade = false) {
    jQuery
      .ajax({
        dataType: 'json',
        url: yaymail_notice.admin_ajax,
        type: 'post',
        data: {
          action: isUpgrade
            ? 'yaymail_dismiss_upgrade_notice'
            : 'yaymail_dismiss_suggest_addons_notice',
          nonce: yaymail_notice.nonce,
        },
      })
      .done(function (result) {
        if (result.success) {
          console.log('success hide notice');
        } else {
          console.log('Error', result.message);
        }
      })
      .fail(function (res) {
        console.log(res.responseText);
      });
  }
});
