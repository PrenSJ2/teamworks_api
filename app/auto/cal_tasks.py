from datetime import datetime, timedelta

import logfire

from app.auto._utils import app_logger
from app.cal.tasks import renew_notification_channel, sync_calendar_events
from app.cal.views import set_google_calendar_id
from app.firebase_setup import db
from app.models import PropertyCal
from app.utils import settings


def auto_check_and_renew_channels():
    with logfire.span('auto_check_and_renew_channels'):
        # Iterate over all property documents
        properties_ref = db.collection('properties').stream()
        for prop in properties_ref:
            app_logger.info('Renewing channel for property: %s', prop.id)
            calendar_id = prop.get('externalCalendar')

            # Check if 'channelId' exists in the property document
            if 'channelId' not in prop.to_dict():
                app_logger.warning('Property %s does not contain channelId', prop.id)
                continue

            channel_id = prop.get('channelId')
            channel_address = settings.url + calendar_id
            try:
                new_channel, expiration = renew_notification_channel(calendar_id, channel_id, 'web_hook', channel_address)
                if not new_channel or not expiration:
                    app_logger.error('Failed to renew channel for property: %s. Invalid response from renew_notification_channel.', prop.id)
                    continue
            except Exception as e:
                app_logger.error('Error renewing channel for property: %s', prop.id)
                app_logger.error(e)
                continue

            # Update the property document with the new channel id and expiration time
            prop.reference.update({'channelId': new_channel['id'], 'channelExpiration': expiration})

            app_logger.info('Channel for property: %s successfully renewed', prop.id)

def resync_all_calendar_events():
    """
    Resync all calendar events for all
    """
    with logfire.span('resync_all_calendar_events'):

        # Iterate over all property documents
        properties_ref = db.collection('properties').stream()
        for prop in properties_ref:
            try:
                sync_calendar_events(prop.reference)
            except Exception as e:
                app_logger.error('Error syncing calendar events for property: %s', prop.id)
                app_logger.error(e)
                continue
            app_logger.info('Calendar events for property: %s successfully synced', prop.id)

        app_logger.info('All calendar events successfully synced')